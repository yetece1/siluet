from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

from .anonymizer import AnonymizationSession
from .project import FileEntry, FileGroup, Project


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _flat_targets(groups: list[FileGroup], output_root: Path) -> dict[str, Path]:
    """Resolve a single flat output directory without renaming or overwriting."""
    targets: dict[str, Path] = {}
    for group in groups:
        for entry in group.files:
            source = Path(entry.path)
            key = source.name.casefold()
            if key in targets and targets[key] != source.resolve():
                raise ValueError(f"Aynı adlı iki kaynak tek klasöre yazılamaz: {source.name}")
            target = output_root / source.name
            if target.resolve() == source.resolve():
                raise ValueError("Çıktı klasörü kaynak dosyanın bulunduğu klasör olamaz")
            if target.exists():
                raise FileExistsError(f"Çıktı klasöründe aynı adlı dosya zaten var: {source.name}")
            targets[key] = source.resolve()
    return {key: output_root / source.name for key, source in targets.items()}


def _safe_error_message(exc: Exception) -> str:
    """Kişisel hücre içeriğini göstermeden kullanıcıya işe yarar neden verir."""
    known = {
        "FileNotFoundError": "Kaynak dosya bulunamadı.",
        "PermissionError": "Dosya erişim izni reddedildi veya dosya başka bir uygulamada açık.",
        "BadZipFile": "Dosya geçerli bir XLSX çalışma kitabı değil veya hasarlı.",
        "InvalidFileException": "Excel dosya biçimi desteklenmiyor.",
        "KeyError": "Çalışma kitabının iç yapısı okunamadı.",
    }
    if type(exc).__name__ in known:
        return known[type(exc).__name__]
    if isinstance(exc, RuntimeError) and str(exc):
        return str(exc)
    return "Dosya işlenemedi; teknik tür: " + type(exc).__name__


@dataclass
class FileProcessingContext:
    source: Path
    entry: FileEntry
    output: Path | None = None
    source_fingerprint: str = ""
    status: str = "bekliyor"
    error_type: str | None = None
    error_message: str | None = None

    def capture_source(self) -> None:
        self.source_fingerprint = _fingerprint(self.source)

    def verify_source(self) -> None:
        if _fingerprint(self.source) != self.source_fingerprint:
            raise RuntimeError("Orijinal dosya değişti")


@dataclass
class GroupResult:
    group_id: str
    group_name: str
    files: list[FileProcessingContext] = field(default_factory=list)
    successful: bool = False

    def safe_dict(self) -> dict:
        return {
            "group_id": self.group_id, "group_name": self.group_name, "successful": self.successful,
            "files": [{"file_id": f"file-{index:03d}", "role": x.entry.role, "status": x.status,
                       "output_created": bool(x.output and x.output.exists()), "error_type": x.error_type,
                       "error_message": x.error_message} for index, x in enumerate(self.files, 1)],
        }


class GroupProcessor:
    def __init__(self, project: Project, output_root: Path, cancel_event: threading.Event | None = None,
                 progress=None, continue_on_error: bool = False):
        self.project, self.output_root = project, output_root
        self.cancel_event = cancel_event or threading.Event()
        self.progress = progress or (lambda *_args: None)
        self.continue_on_error = continue_on_error

    def process(self, group_ids: list[str] | None = None) -> list[GroupResult]:
        selected = [g for g in self.project.groups if group_ids is None or g.group_id in group_ids]
        self.output_root.mkdir(parents=True, exist_ok=True)
        targets = _flat_targets(selected, self.output_root)
        total = sum(len(g.files) for g in selected); completed = 0; results = []
        for group in selected:
            result = self._process_group(group, completed, total, targets)
            completed += len(group.files); results.append(result)
            if not result.successful and not self.continue_on_error: break
        return results

    def _process_group(self, group: FileGroup, offset: int, total: int, targets: dict[str, Path]) -> GroupResult:
        result = GroupResult(group.group_id, group.name)
        contexts = [FileProcessingContext(Path(e.path), e) for e in group.files]
        result.files = contexts
        secret, surnames, state = self.project.mapping_context(group.group_id)
        session = AnonymizationSession(self.project, self.cancel_event,
            lambda done, _count, name: self.progress(offset + done, total, group.name, name),
            secret, surnames, state)
        valid_paths = []
        for context in contexts:
            try:
                if not context.source.is_file(): raise FileNotFoundError
                probe = load_workbook(context.source, read_only=True, data_only=False)
                probe.close(); valid_paths.append(context.source)
            except Exception as exc:
                context.status, context.error_type = "başarısız", type(exc).__name__
                context.error_message = _safe_error_message(exc)
        try:
            session.prepare(valid_paths)
            for index, context in enumerate(contexts, 1):
                if context.status == "başarısız":
                    self.progress(offset + index, total, group.name, context.source.name)
                    if not self.continue_on_error: break
                    continue
                if self.cancel_event.is_set(): raise InterruptedError("İşlem iptal edildi")
                self.progress(offset + index - 1, total, group.name, context.source.name)
                try:
                    if not context.source.is_file(): raise FileNotFoundError("Girdi dosyası bulunamadı")
                    context.capture_source()
                    context.output = targets[context.source.name.casefold()]
                    selected = set(context.entry.sheets) if context.entry.sheets else None
                    session.anonymize_file(context.source, context.output, selected)
                    context.verify_source(); context.status = "başarılı"
                except InterruptedError:
                    if context.output: context.output.unlink(missing_ok=True)
                    raise
                except Exception as exc:
                    if context.output: context.output.unlink(missing_ok=True)
                    context.status, context.error_type = "başarısız", type(exc).__name__
                    context.error_message = _safe_error_message(exc)
                    if not self.continue_on_error: break
                finally:
                    self.progress(offset + index, total, group.name, context.source.name)
            self.project.update_mapping_context(group.group_id, session.store.surname_state, session.store.persistent_state)
            self.project.save()
        finally:
            session.report.integrity["mapping_collisions"] = session.report.collisions == 0
            result.successful = bool(contexts) and all(x.status == "başarılı" for x in contexts)
        return result
