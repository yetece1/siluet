"""İşlem sonucu yardımcıları."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def summarize(results) -> tuple[int, list[tuple[str, str]]]:
    ok, failed = 0, []
    for result in results:
        for context in result.files:
            if context.status == "başarılı":
                ok += 1
            else:
                failed.append((context.source.name, context.error_message or "İşlenmedi."))
    return ok, failed


def open_folder(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
