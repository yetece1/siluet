import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import pytest


@pytest.fixture(autouse=True)
def _main_thread_gc(qapp):
    """Uygulamadaki gibi: çöp toplama yalnız ana iş parçacığında."""
    from siluet.ui.app import install_main_thread_gc
    install_main_thread_gc(qapp)
    yield
