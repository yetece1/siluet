"""Qt'den bağımsız arayüz mantığı: dosya toplama ve başlatma öncesi kontroller."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..project import Project


def _is_candidate(path: Path) -> bool:
    return path.suffix.casefold() == ".xlsx" and not path.name.startswith("~$")


@dataclass
class CollectReport:
    files: list[Path] = field(default_factory=list)
    skipped_files: int = 0        # xlsx olmayan veya geçici dosyalar
    skipped_folders: int = 0      # taranmayan alt klasörler
    unreadable: list[Path] = field(default_factory=list)  # içi okunamayan klasörler


def collect_xlsx_report(paths: list[Path]) -> CollectReport:
    """Verilen dosyaları ve klasörlerin doğrudan çocuklarını toplar; alt klasörlere inilmez."""
    found: dict[str, Path] = {}
    skipped: set[str] = set()
    report = CollectReport()

    def consider(path: Path) -> None:
        key = os.path.normcase(str(path.resolve()))
        if _is_candidate(path):
            found.setdefault(key, path.resolve())
        else:
            skipped.add(key)

    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            try:
                children = list(path.iterdir())
            except OSError:
                report.unreadable.append(path)
                continue
            for child in children:
                if child.is_file():
                    consider(child)
                elif child.is_dir():
                    report.skipped_folders += 1
        elif path.is_file():
            consider(path)
    report.files = sorted(found.values(), key=lambda p: (p.parent.as_posix().casefold(), p.name.casefold()))
    report.skipped_files = len(skipped)
    return report


def collect_xlsx(paths: list[Path]) -> tuple[list[Path], int]:
    report = collect_xlsx_report(paths)
    return report.files, report.skipped_files


@dataclass(frozen=True)
class Blocker:
    code: str
    message: str
    detail: str = ""  # arayüzün kendi dilinde metin kurması için: dosya adları veya sayı


def _writable(folder: Path) -> bool:
    probe_dir = folder
    while not probe_dir.exists():
        if probe_dir.parent == probe_dir:
            return False
        probe_dir = probe_dir.parent
    if not probe_dir.is_dir():
        return False
    try:
        fd, name = tempfile.mkstemp(prefix=".hts-yazma-", dir=probe_dir)
    except OSError:
        return False
    os.close(fd)
    os.unlink(name)
    return True


def preflight(project: Project, output_dir: Path | None, pending_ambiguous: int) -> list[Blocker]:
    entries = [Path(entry.path) for group in project.groups for entry in group.files]
    if pending_ambiguous:
        return [Blocker("ambiguous_pending", f"{pending_ambiguous} dosyanın türünü (ana/karşı baz) seçin.",
                        str(pending_ambiguous))]
    if not entries:
        return [Blocker("no_files", "En az bir Excel dosyası ekleyin.")]
    missing = [p.name for p in entries if not p.is_file()]
    if missing:
        names = ", ".join(missing[:3]) + (f" (+{len(missing) - 3})" if len(missing) > 3 else "")
        return [Blocker("source_missing", "Kaynak dosya bulunamadı: " + names, names)]
    seen: dict[str, Path] = {}
    for path in entries:
        key = path.name.casefold()
        if key in seen and seen[key] != path:
            return [Blocker("duplicate_names", f"Aynı adlı iki kaynak tek çıktı klasörüne yazılamaz: {path.name}", path.name)]
        seen[key] = path
    if output_dir is None:
        return [Blocker("no_output", "Çıktı klasörünü seçin.")]
    output = Path(output_dir).resolve()
    source_dirs = {os.path.normcase(str(p.resolve().parent)) for p in entries}
    blockers: list[Blocker] = []
    if os.path.normcase(str(output)) in source_dirs:
        blockers.append(Blocker("output_inside_source", "Çıktı klasörü kaynak dosyaların bulunduğu klasör olamaz."))
    if not _writable(output):
        blockers.append(Blocker("output_not_writable", "Çıktı klasörüne yazılamıyor."))
    if output.is_dir():
        existing = sorted(p.name for p in entries if (output / p.name).exists())
        if existing and not blockers:
            names = ", ".join(existing[:3]) + (f" (+{len(existing) - 3})" if len(existing) > 3 else "")
            blockers.append(Blocker("output_exists",
                                    "Çıktı klasöründe aynı adlı dosya var (başka klasör seçin veya taşıyın): " + names, names))
    return blockers
