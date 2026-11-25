from __future__ import annotations

import os
import re
import tempfile
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell

from .detector import SYSTEM_LITERALS, Section, detect_sections
from .mapping_store import MappingStore
from .normalization import digits, fold, normalize_classified_value
from .project import Project
from .report import AuditReport
from .sanitizer import has_unsafe_text, sanitize_text
from .synthetic import SyntheticFactory
from .text_anonymizer import TextAnonymizer
from .validators import validate_structure


PHONE_RE = re.compile(r"(?<!\d)(?:\+?90[\s()-]*)?0?\d{3}[\s()-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)")
IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
PRESERVED_CATEGORIES = {"base", "name", "serial", "preserve_type", "event_date", "duration", "status", "operator", "byte_size"}
JUDICIAL_TOKENS = ("mahkeme", "hakimlik", "savcilik", "bassavcilik", "agir ceza", "sulh ceza", "asliye ceza", "adliye")
JUDICIAL_LABELS = {"mahkeme", "mahkeme adi", "hakimlik", "savcilik", "bassavcilik", "talep eden makam", "adli makam"}


def is_system_literal(value: object) -> bool:
    text = fold(value)
    # Sabit ifade hücrenin neresinde bulunursa bulunsun hücrenin tamamı korunur.
    return not text or any(literal in text for literal in SYSTEM_LITERALS)


TITLE_SUFFIXES = {"av", "av.", "dr", "dr.", "prof", "prof.", "hakim", "hâkim", "savci", "savcı", "bey", "hanim", "hanım"}


def _split_full_name(value: str) -> tuple[str, str, str] | None:
    parts = value.strip().split()
    if len(parts) < 2:
        return None
    suffix: list[str] = []
    while len(parts) >= 2 and fold(parts[-1]) in {fold(x) for x in TITLE_SUFFIXES}:
        suffix.insert(0, parts.pop())
    return (" ".join(parts[:-1]), parts[-1], " ".join(suffix)) if len(parts) >= 2 else None


class AnonymizationSession:
    def __init__(self, project: Project, cancel_event: threading.Event | None = None, progress=None,
                 secret: bytes | None = None, surname_state: dict[str, str] | None = None,
                 mapping_state: dict[str, dict[str, str]] | None = None):
        self.project = project
        self.store = MappingStore(secret or project.secret,
                                  project.surname_mappings if surname_state is None else surname_state,
                                  project.mapping_state if mapping_state is None else mapping_state)
        self.text_anonymizer = TextAnonymizer(self.store)
        self.synthetic = SyntheticFactory(self.store)
        self.report = AuditReport()
        self.cancel_event = cancel_event or threading.Event()
        self.progress = progress or (lambda *_args: None)
        self.original_fingerprints: set[str] = set()

    def _check_cancelled(self):
        if self.cancel_event.is_set():
            raise InterruptedError("İşlem kullanıcı tarafından iptal edildi")

    def prepare(self, paths: list[Path]) -> None:
        surnames: list[str] = []
        for path in paths:
            self._check_cancelled()
            wb = load_workbook(path, data_only=False, read_only=False)
            try:
                for ws in wb.worksheets:
                    self._check_cancelled()
                    sections = detect_sections(ws)
                    for section in sections:
                        for col, header in section.raw_headers.items():
                            override = self.project.field_overrides.get(fold(header))
                            if override:
                                section.columns[col] = override
                    for section in sections:
                        if not section.header_row:
                            continue
                        for col, category in section.columns.items():
                            if category not in {"surname", "full_name"}:
                                continue
                            for row in range(section.header_row + 1, section.end_row + 1):
                                if row % 500 == 0:
                                    self._check_cancelled()
                                value = ws.cell(row, col).value
                                if not isinstance(value, str) or is_system_literal(value):
                                    continue
                                if category == "surname":
                                    surnames.append(value)
                                else:
                                    split = _split_full_name(value)
                                    if split:
                                        surnames.append(split[1])
            finally:
                wb.close()
        self.store.prepare_surnames(surnames)

    def _transform(self, value, category: str, section: Section):
        if value is None or is_system_literal(value) or category in PRESERVED_CATEGORIES:
            return value
        normalized_value, simplified = normalize_classified_value(value, category)
        if simplified:
            self.report.simplified_cells[category] += 1
            if category == "phone":
                self.report.simplified_phone_cells += 1
        text = sanitize_text(str(normalized_value)) if isinstance(normalized_value, str) else str(normalized_value)
        if category == "phone":
            result = self.store.phone(text)
            output_digits = re.sub(r"\D", "", result)
            if len(output_digits) > 15:
                raise RuntimeError("Telefon alanı tek bir numaraya sadeleştirilemedi")
            return result
        if category == "tc": return self.store.tc(text)
        if category == "surname": return self.store.surname(text)
        if category == "full_name":
            split = _split_full_name(text)
            if not split:
                return self._generic(text, "full-name")
            result = f"{split[0]} {self.store.surname(split[1])}"
            return f"{result} {split[2]}" if split[2] else result
        if category in {"mother", "father"}: return self.store.related_name(text, category)
        if category == "address": return self.synthetic.address(text)
        if category in {"birth_place", "personal_city", "personal_district"}: return self.synthetic.place(text)
        if category == "birth_date":
            offset = 30 + int.from_bytes(self.store.digest("birth-date", text)[:2], "big") % 300
            if isinstance(value, datetime): return value + timedelta(days=offset)
            if isinstance(value, date): return value + timedelta(days=offset)
            return self.synthetic.date_value(value)
        if category == "imei": return self.store.imei(text)
        if category == "imsi": return self.store.numeric_identifier(text, "imsi")
        if category == "iccid": return self.store.numeric_identifier(text, "iccid")
        if category == "mac": return self.store.formatted_identifier(text, "mac")
        if category == "ip":
            # IP:port biçiminde portu koru.
            if ":" in text and text.count(":") == 1:
                host, port = text.rsplit(":", 1)
                if port.isdigit(): return f"{self.store.ip(host)}:{port}"
            return self.store.ip(text)
        if category == "url": return self.store.url(text, mode="domain")
        if category == "free_text": return self.text_anonymizer.transform(text)[0]
        if category == "location": return self.store.formatted_identifier(text, "personal-location")
        if category in {"gateway", "switch", "pin", "identifier", "file_number"}:
            return self.store.numeric_identifier(text, category) if any(c.isdigit() for c in text) else self.store.token(text, category)
        if category in {"institution", "court"}: return ""
        if category == "serial": return self.synthetic.serial(value)
        if category == "call_type": return self.synthetic.call_type(value)
        if category == "event_date": return self.synthetic.date_value(value)
        if category == "duration": return self.synthetic.duration(value)
        if category == "status": return self.synthetic.status(value)
        if category == "operator": return self.synthetic.operator(value)
        if category == "byte_size": return self.synthetic.byte_size(value)
        return self._generic(value, category)

    def _generic(self, value, namespace: str = "generic"):
        """Tanınmayan/bozuk hassas değeri gerçek haliyle bırakmayan son güvenlik katmanı."""
        if isinstance(value, datetime):
            days = 1 + int.from_bytes(self.store.digest(namespace, value.isoformat())[:2], "big") % 365
            return value + timedelta(days=days)
        if isinstance(value, date):
            days = 1 + int.from_bytes(self.store.digest(namespace, value.isoformat())[:2], "big") % 365
            return value + timedelta(days=days)
        text = sanitize_text(str(value))
        if len(digits(text)) >= 4:
            return self.store.numeric_identifier(text, f"generic:{namespace}")
        return self.store.token(text, f"generic:{namespace}")

    def _replace_embedded(self, value: str) -> str:
        return self.text_anonymizer.transform(value)[0]

    def anonymize_file(self, input_path: Path, output_path: Path, selected_sheets: set[str] | None = None) -> None:
        wb = load_workbook(input_path, data_only=False, read_only=False, keep_links=True)
        try:
            self._anonymize_open_workbook(wb, input_path, output_path, selected_sheets)
        finally:
            wb.close()

    def _anonymize_open_workbook(self, wb, input_path: Path, output_path: Path, selected_sheets: set[str] | None = None) -> None:
        # Belge özellikleri hücrelerden bağımsız kişisel veri taşıyabilir.
        for attribute in ("creator", "lastModifiedBy", "title", "subject", "description", "keywords", "category"):
            setattr(wb.properties, attribute, None)
        self.report.files += 1
        self.report.sheets += sum(selected_sheets is None or ws.title in selected_sheets for ws in wb.worksheets)
        recognized_content = False
        for sheet_index, ws in enumerate(wb.worksheets, 1):
            self._check_cancelled()
            if selected_sheets is not None and ws.title not in selected_sheets:
                continue
            sections = detect_sections(ws)
            if any(section.title_row > 0 or section.header_row is not None for section in sections):
                recognized_content = True
            if not recognized_content and any(is_system_literal(cell.value) and fold(cell.value) for row in ws.iter_rows() for cell in row):
                recognized_content = True
            for section in sections:
                for col, header in section.raw_headers.items():
                    override = self.project.field_overrides.get(fold(header))
                    if override:
                        section.columns[col] = override
            self.report.rows += ws.max_row
            classified_coords: set[tuple[int, int]] = set()
            base_values: dict[tuple[int, int], object] = {}
            verbatim_values: dict[tuple[int, int], object] = {}
            for section_index, section in enumerate(sections, 1):
                self.report.sections.append({"sheet_index": sheet_index, "section_index": section_index,
                                             "title_row": section.title_row, "header_row": section.header_row})
                if not section.header_row:
                    continue
                for col, raw_header in section.raw_headers.items():
                    if col not in section.columns and raw_header.strip():
                        self.report.unknown_columns.append({"sheet_index": sheet_index, "section_row": section.title_row, "column": col})
                for row in range(section.header_row + 1, section.end_row + 1):
                    for col, category in section.columns.items():
                        self._check_cancelled()
                        classified_coords.add((row, col))
                        cell = ws.cell(row, col)
                        if isinstance(cell, MergedCell):
                            continue
                        if cell.value is None:
                            self.report.empty_cells += 1
                            continue
                        if category == "base":
                            base_values[(row, col)] = cell.value
                            verbatim_values[(row, col)] = cell.value
                            self.report.protected_base_cells += 1
                            continue
                        original = cell.value
                        if cell.data_type == "f":
                            continue
                        if category in PRESERVED_CATEGORIES or is_system_literal(original):
                            verbatim_values[(row, col)] = original
                        replacement = self._transform(original, category, section)
                        if replacement == original and category not in PRESERVED_CATEGORIES and not is_system_literal(original):
                            replacement = self._generic(original, category)
                        if replacement == original and category not in PRESERVED_CATEGORIES and not is_system_literal(original):
                            raise RuntimeError("Hassas bir hücre anonimleştirilemedi")
                        if replacement != original:
                            cell.value = replacement
                            self.report.changed[category] += 1
            protected_coords = {(s.header_row, c) for s in sections if s.header_row for c in range(1, ws.max_column + 1)}
            protected_coords |= {(s.title_row, c) for s in sections for c in range(1, ws.max_column + 1)}
            # Üst bilgi etiket taraması tablo/veri/başlık hücrelerine uygulanamaz. Aksi
            # halde örneğin adında "Mahkeme" geçen bir BAZ kaydı üst bilgi
            # sanılarak silinir ve BAZ bütünlük kontrolü işlemi durdurur.
            metadata_coords = self._anonymize_metadata(ws, classified_coords | protected_coords)
            # Dinamik başlık algılayıcının gerçek bir adli makam değerini başlık
            # sanması halinde dahi ikinci güvenlik katmanı değeri kaldırır. BAZ
            # hücreleri (örn. "Adliye yanı" veya "... Mah.") kesinlikle muafdır.
            for row in ws.iter_rows():
                for cell in row:
                    coord = (cell.row, cell.column)
                    if coord in base_values or isinstance(cell, MergedCell) or not isinstance(cell.value, str) or is_system_literal(cell.value):
                        continue
                    normalized = fold(cell.value)
                    if normalized not in JUDICIAL_LABELS and any(token in normalized for token in JUDICIAL_TOKENS):
                        cell.value = ""
                        verbatim_values.pop(coord, None)
                        metadata_coords.add(coord)
                        self.report.changed["judicial_removed"] += 1
            # Serbest metin taraması: başlık, bölüm başlığı ve formülleri atla.
            for row in ws.iter_rows():
                for cell in row:
                    if (cell.row, cell.column) in protected_coords or (cell.row, cell.column) in classified_coords or (cell.row, cell.column) in metadata_coords or cell.data_type == "f" or not isinstance(cell.value, str) or is_system_literal(cell.value):
                        continue
                    cleaned = sanitize_text(cell.value)
                    if cleaned != cell.value:
                        self.report.sanitized_cells += 1
                    before_counts = self.text_anonymizer.counts(cleaned)
                    self.original_fingerprints.update(self.text_anonymizer.fingerprints(cleaned))
                    transformed, _ = self.text_anonymizer.transform(cleaned)
                    after_counts = self.text_anonymizer.counts(transformed)
                    if before_counts != after_counts:
                        self.report.identifier_count_errors += 1
                        raise RuntimeError("Bir hücredeki tanımlayıcı sayısı beklenmedik biçimde değişti")
                    if transformed != cell.value:
                        cell.value = transformed
                        self.report.changed["embedded"] += 1
            # Kaydetmeden hemen önce güvenli metin temizliği; baz ve formüller muaf.
            for row in ws.iter_rows():
                for cell in row:
                    if cell.comment is not None:
                        cell.comment = None
                        self.report.changed["comments_removed"] += 1
                    if cell.hyperlink is not None and (cell.row, cell.column) not in base_values:
                        cell.hyperlink = None
                        self.report.changed["hyperlinks_removed"] += 1
                    coord = (cell.row, cell.column)
                    if coord in verbatim_values or coord in protected_coords or cell.data_type == "f" or not isinstance(cell.value, str) or is_system_literal(cell.value):
                        continue
                    cleaned = sanitize_text(cell.value)
                    if cleaned != cell.value:
                        cell.value = cleaned
                        self.report.sanitized_cells += 1
            for coord, original in verbatim_values.items():
                if ws.cell(*coord).value != original:
                    raise RuntimeError("Korunması gereken bir hücre değişti")
        if not recognized_content:
            raise RuntimeError("HTS bölüm veya sütun yapısı tanınamadı; güvenli çıktı üretilemedi")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=".hts-", suffix=".xlsx", dir=output_path.parent)
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            wb.save(temporary)
            self._validate_reopened(temporary)
            validation = validate_structure(input_path, temporary)
            self.report.integrity.update({
                "structure_preserved": validation.structure_preserved,
                "row_order_preserved": validation.row_order_preserved,
                "formula_preserved": validation.no_formula_loss,
            })
            if not validation.ok:
                raise RuntimeError("Bütünlük doğrulaması başarısız")
            self._check_cancelled()
            if output_path.exists():
                raise FileExistsError(f"Çıktı dosyası işlem sırasında oluşturuldu: {output_path.name}")
            os.replace(temporary, output_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _validate_reopened(self, path: Path) -> None:
        wb = load_workbook(path, data_only=False, read_only=False)
        unsafe = 0
        for ws in wb.worksheets:
            sections = detect_sections(ws)
            base = {(r, c) for s in sections if s.header_row for c, kind in s.columns.items() if kind == "base" for r in range(s.header_row + 1, s.end_row + 1)}
            classified = {(r, c) for s in sections if s.header_row for c in s.columns for r in range(s.header_row + 1, s.end_row + 1)}
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and (cell.row, cell.column) not in base:
                        if has_unsafe_text(cell.value):
                            unsafe += 1
                        if (cell.row, cell.column) not in classified and not is_system_literal(cell.value):
                            remaining = self.text_anonymizer.fingerprints(cell.value) & self.original_fingerprints
                            for _fingerprint in remaining:
                                self.report.residual_findings.append({"sheet": ws.title, "row": cell.row, "column": cell.column, "type": "identifier"})
        if unsafe:
            raise RuntimeError("Çıktıda geçersiz satır sonu veya kontrol karakteri kaldı")
        if self.report.residual_findings:
            raise RuntimeError("Çıktıda anonimleştirilmemiş gömülü tanımlayıcı kaldı")
        self.report.integrity["unsafe_text_absent"] = True

    def _anonymize_metadata(self, ws, table_coords: set[tuple[int, int]] | None = None) -> set[tuple[int, int]]:
        """Üst bilgi etiketlerinin sağındaki değeri, gerçek değeri loglamadan dönüştürür."""
        institution_labels = ("talep eden makam", "kurum adi")
        court_labels = ("mahkeme", "hakimlik", "adliye", "savcilik", "bassavcilik")
        file_labels = ("dosya no", "esas no", "karar no", "sorusturma no", "yazi no", "evrak no", "ilgili yazi")
        processed: set[tuple[int, int]] = set()
        table_coords = table_coords or set()
        for row in ws.iter_rows():
            for cell in row:
                if (cell.row, cell.column) in table_coords:
                    continue
                if isinstance(cell, MergedCell):
                    continue
                if not isinstance(cell.value, str):
                    continue
                # Kullanıcı kuralı: sabit sistem ifadesi hücrenin neresinde
                # olursa olsun, adli makam sözcükleri içerse dahi aynen kalır.
                if is_system_literal(cell.value):
                    continue
                label = fold(cell.value)
                category = None
                if any(x in label for x in court_labels): category = "court"
                elif any(x in label for x in institution_labels): category = "institution"
                elif any(x in label for x in file_labels): category = "file_number"
                if category is None:
                    continue
                processed.add((cell.row, cell.column))
                if category == "court":
                    cell.value = ""
                    self.report.changed["court_removed"] += 1
                    continue
                # Etiket ile değer aynı hücredeyse iki nokta sonrasını değiştir.
                if ":" in cell.value:
                    left, right = cell.value.split(":", 1)
                    if right.strip():
                        replacement = self._transform(right.strip(), category, Section("UST BILGI", cell.row))
                        cell.value = f"{left}: {replacement}"
                        self.report.changed[category] += 1
                        continue
                # Şablonda etiket A, değer B hücresindedir.
                neighbor = ws.cell(cell.row, cell.column + 1)
                if (neighbor.row, neighbor.column) in table_coords:
                    continue
                if isinstance(neighbor, MergedCell):
                    continue
                if neighbor.value is not None and not is_system_literal(neighbor.value) and neighbor.data_type != "f":
                    original = neighbor.value
                    replacement = self._transform(original, category, Section("UST BILGI", cell.row))
                    if replacement != original:
                        neighbor.value = replacement
                        self.report.changed[category] += 1
                        processed.add((neighbor.row, neighbor.column))
        return processed

    def run(self, inputs: list[Path], output_dir: Path, sheet_selection: dict[Path, set[str]] | None = None) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        names: set[str] = set()
        for source in inputs:
            key = source.name.casefold()
            if key in names:
                raise ValueError(f"Aynı adlı iki kaynak tek klasöre yazılamaz: {source.name}")
            target = output_dir / source.name
            if target.resolve() == source.resolve():
                raise ValueError("Çıktı klasörü kaynak dosyanın bulunduğu klasör olamaz")
            if target.exists():
                raise FileExistsError(f"Çıktı klasöründe aynı adlı dosya zaten var: {source.name}")
            names.add(key)
        self.prepare(inputs)
        outputs: list[Path] = []
        try:
            for index, source in enumerate(inputs, 1):
                self._check_cancelled()
                self.progress(index - 1, len(inputs), source.name)
                target = output_dir / source.name
                selected = (sheet_selection or {}).get(source)
                self.anonymize_file(source, target, selected)
                outputs.append(target)
            self.project.surname_mappings = self.store.surname_state
            self.project.mapping_state = self.store.persistent_state
            self.project.save()
            self.progress(len(inputs), len(inputs), "Tamamlandı")
        except Exception:
            for output in outputs:
                output.unlink(missing_ok=True)
            raise
        self.report.integrity["mapping_collisions"] = self.report.collisions == 0
        return outputs
