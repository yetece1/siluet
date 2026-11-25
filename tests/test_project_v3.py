from pathlib import Path
import base64
import hashlib
import json
import os

import pytest

from siluet import project as project_module
from siluet.crypto_store import WrongPasswordError
from siluet.project import (
    LOCK_FILE, PROJECT_FILE, LegacyProjectError, Project, ProjectLockedError, ROLE_MAIN,
)

from conftest import TEST_PASSWORD


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build(tmp_path):
    project = Project.create(tmp_path / "proje", TEST_PASSWORD)
    group = project.add_group("Gizli İnceleme Adı")
    source = tmp_path / "ALI_YILMAZ_hts.xlsx"
    source.write_bytes(b"x")
    project.add_file(group.group_id, source, ROLE_MAIN, ["Sheet0"])
    project.mapping_state = {"imei-core": {"h1": "86123"}}
    project.save()
    return project, group


def test_create_and_reopen_roundtrip(tmp_path):
    project, group = _build(tmp_path)
    secret = project.secret
    project.close()
    reopened = Project.open(tmp_path / "proje", TEST_PASSWORD)
    assert reopened.secret == secret
    assert [g.name for g in reopened.groups] == ["Gizli İnceleme Adı"]
    assert reopened.groups[0].files[0].role == ROLE_MAIN
    assert reopened.mapping_state == {"imei-core": {"h1": "86123"}}
    reopened.close()


def test_wrong_password_leaves_file_untouched(tmp_path):
    project, _ = _build(tmp_path)
    project.close()
    path = tmp_path / "proje" / PROJECT_FILE
    before = _digest(path)
    with pytest.raises(WrongPasswordError):
        Project.open(tmp_path / "proje", "yanlis-parola-xyz")
    assert _digest(path) == before
    Project.open(tmp_path / "proje", TEST_PASSWORD).close()


def test_file_has_no_plaintext(tmp_path):
    project, _ = _build(tmp_path)
    text = (tmp_path / "proje" / PROJECT_FILE).read_text(encoding="utf-8")
    for forbidden in ("Gizli", "ALI_YILMAZ", "86123", base64.urlsafe_b64encode(project.secret).decode(),
                      base64.b64encode(project.secret).decode()):
        assert forbidden not in text
    assert json.loads(text)["version"] == 3
    project.close()


def test_change_password(tmp_path):
    project, _ = _build(tmp_path)
    with pytest.raises(WrongPasswordError):
        project.change_password("yanlis-parola-xyz", "yeni-parola-2026", "yeni-parola-2026")
    with pytest.raises(ValueError):
        project.change_password(TEST_PASSWORD, "kisa", "kisa")
    project.change_password(TEST_PASSWORD, "yeni-parola-2026", "yeni-parola-2026")
    project.close()
    with pytest.raises(WrongPasswordError):
        Project.open(tmp_path / "proje", TEST_PASSWORD)
    Project.open(tmp_path / "proje", "yeni-parola-2026").close()


def test_atomic_save_failure_keeps_old_file(tmp_path, monkeypatch):
    project, _ = _build(tmp_path)
    folder = tmp_path / "proje"
    before = _digest(folder / PROJECT_FILE)
    def boom(*_args):
        raise OSError("disk dolu")
    monkeypatch.setattr(project_module.os, "replace", boom)
    with pytest.raises(OSError):
        project.save()
    monkeypatch.undo()
    assert _digest(folder / PROJECT_FILE) == before
    assert not [p for p in folder.iterdir() if p.suffix == ".tmp"]
    project.close()
    Project.open(folder, TEST_PASSWORD).close()


def test_second_open_locked(tmp_path):
    project, _ = _build(tmp_path)
    with pytest.raises(ProjectLockedError):
        Project.open(tmp_path / "proje", TEST_PASSWORD)
    project.close()
    Project.open(tmp_path / "proje", TEST_PASSWORD).close()


def _hold_lock_in_subprocess(folder):
    import subprocess, sys
    code = ("import sys, time; from pathlib import Path; from siluet.project import _acquire_lock; "
            "_acquire_lock(Path(sys.argv[1])); print('kilitli', flush=True); time.sleep(60)")
    proc = subprocess.Popen([sys.executable, "-c", code, str(folder)], stdout=subprocess.PIPE, text=True,
                            cwd=str(Path(__file__).resolve().parents[1]))
    assert proc.stdout.readline().strip() == "kilitli"
    return proc


def test_lock_held_by_other_process(tmp_path):
    project, _ = _build(tmp_path)
    project.close()
    holder = _hold_lock_in_subprocess(tmp_path / "proje")
    try:
        with pytest.raises(ProjectLockedError):
            Project.open(tmp_path / "proje", TEST_PASSWORD)
    finally:
        holder.kill(); holder.wait()
    # Kilit sahibi süreç çöktüğünde (kill) işletim sistemi kilidi bırakır.
    Project.open(tmp_path / "proje", TEST_PASSWORD).close()


def test_leftover_lock_file_without_os_lock_is_taken_over(tmp_path):
    """Elektrik kesintisi sonrası kalan dosya; içindeki PID başka bir canlı sürece ait olsa bile."""
    project, _ = _build(tmp_path)
    project.close()
    import socket
    (tmp_path / "proje" / LOCK_FILE).write_text(json.dumps({"pid": os.getppid(), "host": socket.gethostname()}))
    reopened = Project.open(tmp_path / "proje", TEST_PASSWORD)
    reopened.close()


def test_empty_lock_file_taken_over(tmp_path):
    project, _ = _build(tmp_path)
    project.close()
    (tmp_path / "proje" / LOCK_FILE).write_text("")
    Project.open(tmp_path / "proje", TEST_PASSWORD).close()


def test_legacy_file_detected(tmp_path):
    folder = tmp_path / "eski"
    folder.mkdir()
    (folder / PROJECT_FILE).write_text(json.dumps({"version": 2, "project_id": "x", "internal_key": "a" * 44}))
    assert Project.detect_version(folder) == 2
    assert Project.detect_version(tmp_path / "yok") is None
    with pytest.raises(LegacyProjectError):
        Project.open(folder, TEST_PASSWORD)


def test_repr_does_not_expose_secret(tmp_path):
    project, _ = _build(tmp_path)
    text = repr(project)
    assert project.secret.hex() not in text and repr(project.secret) not in text
    project.close()
