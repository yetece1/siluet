"""Beklenmeyen hataları kullanıcıya özel bir günlük dosyasına yazar.

Uygulama çift tıklamayla açılıp hemen kapanırsa sebebi bu dosyada görünür.
Hata mesajlarındaki 5 haneden uzun rakam dizileri (telefon, T.C. vb.) maskelenir.
"""
from __future__ import annotations

import datetime
import faulthandler
import os
import platform
import re
import sys
import traceback
from pathlib import Path

APP_DIR = "Siluet"
LOG_NAME = "hata.log"
_DIGITS = re.compile(r"\d{5,}")
_FAULT_HANDLE = None


def log_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / APP_DIR


def _mask(text: str) -> str:
    return _DIGITS.sub(lambda m: "#" * len(m.group()), text)


def install_crash_logging(folder: Path | None = None, native_crashes: bool = False) -> Path:
    global _FAULT_HANDLE
    folder = Path(folder) if folder is not None else log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / LOG_NAME
    previous = sys.excepthook

    def hook(exc_type, exc, tb):
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n=== {datetime.datetime.now().isoformat(timespec='seconds')} ===\n")
                handle.write(f"Python {sys.version.split()[0]} · Platform {platform.platform()}\n")
                handle.write(_mask("".join(traceback.format_exception(exc_type, exc, tb))))
        except OSError:
            pass
        previous(exc_type, exc, tb)

    sys.excepthook = hook
    if not native_crashes:
        return path
    try:
        # Yerel kod çökmeleri (segfault) için yığın dökümü; hücre içeriği içermez.
        if _FAULT_HANDLE is None:
            _FAULT_HANDLE = (folder / "cokme.log").open("a", encoding="utf-8")
            faulthandler.enable(_FAULT_HANDLE)
    except OSError:
        pass
    return path
