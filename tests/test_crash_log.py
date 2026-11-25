import sys

from siluet.crash_log import install_crash_logging, log_dir


def test_log_dir_is_per_user(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    folder = log_dir()
    assert "Siluet" in str(folder)


def test_uncaught_exception_written_to_log(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)
    path = install_crash_logging(tmp_path)
    try:
        raise RuntimeError("deneme hatası")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    text = path.read_text(encoding="utf-8")
    assert "RuntimeError" in text and "deneme hatası" in text
    assert "Python" in text and "Platform" in text


def test_long_digit_runs_are_masked(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)
    path = install_crash_logging(tmp_path)
    try:
        raise ValueError("hücre: 05321234567 / 12345678901")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    text = path.read_text(encoding="utf-8")
    assert "05321234567" not in text and "12345678901" not in text
