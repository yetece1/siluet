from __future__ import annotations

import secrets
import hashlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import load_workbook

from siluet.auto_classifier import classify_files
from siluet.detector import detect_sections
from siluet.group_processor import GroupProcessor
from siluet.normalization import digits, normalize_classified_value
from siluet.mapping_store import MappingStore, split_phone
from siluet.project import Project
from siluet.validators import validate_structure


PRESERVED = {"base", "name", "serial", "preserve_type", "event_date", "duration", "status", "operator", "byte_size"}


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def cell_records(path: Path):
    workbook = load_workbook(path, data_only=False)
    try:
        for sheet in workbook.worksheets:
            for section in detect_sections(sheet):
                if not section.header_row:
                    continue
                for column, category in section.columns.items():
                    header = section.raw_headers.get(column, "")
                    for row in range(section.header_row + 1, section.end_row + 1):
                        yield sheet.title, row, column, header, category, sheet.cell(row, column).value
    finally:
        workbook.close()


def main(source_root: Path, work_root: Path) -> int:
    paths = sorted(
        p for p in source_root.iterdir()
        if p.is_file() and p.suffix.casefold() == ".xlsx"
        and not p.name.startswith("~$")
    )
    if not paths:
        raise SystemExit("XLSX bulunamadı")
    before_hashes = {p: sha256(p) for p in paths}
    groups, ambiguous, failures = classify_files(paths)
    profile_count = sum(len(group.profiles) for group in groups)
    if ambiguous or failures or profile_count != len(paths):
        raise AssertionError(f"Sınıflandırma eksik: groups={profile_count}, ambiguous={len(ambiguous)}, failures={len(failures)}")

    if work_root.exists():
        shutil.rmtree(work_root)
    project_dir, output_dir = work_root / "project", work_root / "output"
    project = Project.create(project_dir, secrets.token_urlsafe(24))  # geçici denetim projesi
    added = project.add_auto_groups(groups)
    if added != len(paths):
        raise AssertionError(f"Projeye eklenen dosya sayısı: {added}/{len(paths)}")
    results = GroupProcessor(project, output_dir).process()
    if not results or not all(result.successful for result in results):
        raise AssertionError("En az bir grup başarısız")

    source_to_output = {}
    categories = Counter()
    changed = Counter()
    raw_mapping = defaultdict(dict)
    full_name_count = 0
    for result in results:
        for context in result.files:
            assert context.output and context.output.is_file()
            source_to_output[context.source] = context.output
            validation = validate_structure(context.source, context.output)
            if not validation.ok:
                raise AssertionError(f"Yapı bozuldu: {context.source.name}")

            source_records = list(cell_records(context.source))
            output_book = load_workbook(context.output, data_only=False)
            try:
                output_values = {
                    (sheet, row, col): output_book[sheet].cell(row, col).value
                    for sheet, row, col, _header, _category, _old in source_records
                }
            finally:
                output_book.close()
            for source in source_records:
                _, row, col, header, category, old = source
                new = output_values[(source[0], row, col)]
                categories[category] += 1
                if old != new:
                    changed[category] += 1
                if category == "generic":
                    raise AssertionError(f"Genel kategori kaldı: {context.source.name} / {header}")
                equivalent_empty = old in (None, "") and new in (None, "")
                if category in PRESERVED and old != new and not equivalent_empty:
                    raise AssertionError(f"Korunan alan değişti: {context.source.name} / {header} / {row}:{col}")
                if category == "full_name" and isinstance(old, str) and old.strip() and isinstance(new, str):
                    old_parts, new_parts = old.split(), new.split()
                    if len(old_parts) >= 2:
                        full_name_count += 1
                        if old_parts[:-1] != new_parts[:-1]:
                            raise AssertionError(f"Ad bölümü bozuldu: {context.source.name} / {row}:{col}")
                        if not re.fullmatch(r"[A-Za-zÇĞİÖŞÜçğıöşü .'-]+", new):
                            raise AssertionError(f"Doğal olmayan ad-soyad: {context.source.name} / {row}:{col}")
                if category == "phone" and old not in (None, ""):
                    normalized_old, _ = normalize_classified_value(old, "phone")
                    old_digits, new_digits = digits(normalized_old), digits(new)
                    if len(old_digits) >= 5 and (split_phone(old_digits)[:2] != split_phone(new_digits)[:2] or len(old_digits) != len(new_digits)):
                        raise AssertionError(f"Telefon biçimi/prefix bozuldu: {context.source.name} / {row}:{col}")
                    if len(old_digits) >= 5 and split_phone(old_digits)[2] == split_phone(new_digits)[2]:
                        raise AssertionError(f"Telefon gövdesi değişmedi: {context.source.name} / {row}:{col}")
                if category == "tc" and old not in (None, ""):
                    normalized_old, _ = normalize_classified_value(old, "tc")
                    old_digits, new_digits = digits(normalized_old), digits(new)
                    if len(old_digits) == 11 and (len(new_digits) != 11 or MappingStore._valid_tckn(new_digits) or old_digits[:10] == new_digits[:10]):
                        raise AssertionError(f"TC kuralı bozuldu: {context.source.name} / {row}:{col}")
                if category in {"imei", "imsi", "ip", "tc", "phone", "surname", "full_name"} and old not in (None, ""):
                    raw_mapping[(result.group_id, category)][str(old)] = str(new)

    for path, digest in before_hashes.items():
        if sha256(path) != digest:
            raise AssertionError(f"Kaynak değişti: {path.name}")

    report = {
        "source_files": len(paths),
        "groups": len(groups),
        "paired_groups": sum(len(group.profiles) == 2 for group in groups),
        "ambiguous": len(ambiguous),
        "failures": len(failures),
        "successful_outputs": len(source_to_output),
        "full_name_cells": full_name_count,
        "categories": dict(categories),
        "changed": dict(changed),
        "source_hashes_preserved": True,
        "structure_preserved": True,
        "generic_columns": categories["generic"],
    }
    (work_root / "deep-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Kullanım: deep_audit.py KAYNAK_KLASOR CALISMA_KLASORU")
    raise SystemExit(main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()))
