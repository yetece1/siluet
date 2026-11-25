import base64
import hashlib
import hmac
import json
import secrets

import pytest

from siluet import migration as migration_module
from siluet.migration import BACKUP_NAME, migrate_legacy, secure_delete
from siluet.project import PROJECT_FILE, Project

NEW_PASSWORD = "yeni-proje-parolasi"


def _legacy_protect(secret: bytes, value: str) -> str:
    """v1.0.0 project.py içindeki _protect ile birebir aynı."""
    raw, nonce, stream, counter = value.encode("utf-8"), secrets.token_bytes(16), b"", 0
    while len(stream) < len(raw):
        stream += hmac.new(secret, b"project-store" + nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest(); counter += 1
    encrypted = bytes(a ^ b for a, b in zip(raw, stream))
    tag = hmac.new(secret, b"project-tag" + nonce + encrypted, hashlib.sha256).digest()[:16]
    return "enc:" + base64.urlsafe_b64encode(nonce + tag + encrypted).decode("ascii")


@pytest.fixture
def legacy_project(tmp_path):
    folder = tmp_path / "eski-proje"
    folder.mkdir()
    secret = secrets.token_bytes(32)
    source = tmp_path / "ana.xlsx"
    source.write_bytes(b"x")
    payload = {
        "version": 2, "project_id": "abc123", "internal_key": base64.urlsafe_b64encode(secret).decode("ascii"),
        "surname_mappings": {}, "mapping_state": {}, "field_overrides": {}, "mapping_scope": "group",
        "groups": [{"group_id": "g1", "name": "Otomatik 001",
                    "files": [{"path": str(source), "role": "main", "sheets": ["Sheet0"]}]}],
        "group_surname_mappings": {"g1": {"h-soyad": _legacy_protect(secret, "Arıner")}},
        "group_mapping_state": {"g1": {"phone": {"h1": "05321230000"}, "tc": {"h2": "12345670000"},
                                       "imei-core": {"h3": "86123456789012"}}},
    }
    (folder / PROJECT_FILE).write_text(json.dumps(payload), encoding="utf-8")
    return folder, secret


def test_migrates_groups_and_keeps_other_mappings(legacy_project):
    folder, secret = legacy_project
    result = migrate_legacy(folder, NEW_PASSWORD, NEW_PASSWORD)
    project = result.project
    assert project.secret == secret
    assert result.dropped_namespaces == ["phone", "tc"]
    assert project.group_mapping_state["g1"] == {"imei-core": {"h3": "86123456789012"}}
    assert project.group_surname_mappings["g1"] == {"h-soyad": "Arıner"}
    assert project.groups[0].files[0].role == "main"
    project.close()
    Project.open(folder, NEW_PASSWORD).close()


def test_backup_written_and_plain_file_replaced(legacy_project):
    folder, _ = legacy_project
    result = migrate_legacy(folder, NEW_PASSWORD, NEW_PASSWORD)
    assert result.backup_path == folder / BACKUP_NAME and result.backup_path.exists()
    assert json.loads(result.backup_path.read_text())["version"] == 2
    assert Project.detect_version(folder) == 3
    result.project.close()


def test_crash_after_backup_keeps_recoverable(legacy_project, monkeypatch):
    folder, _ = legacy_project
    original = (folder / PROJECT_FILE).read_bytes()
    def boom(*_args, **_kwargs):
        raise OSError("disk dolu")
    monkeypatch.setattr(migration_module, "write_atomic_json", boom)
    with pytest.raises(OSError):
        migrate_legacy(folder, NEW_PASSWORD, NEW_PASSWORD)
    monkeypatch.undo()
    assert (folder / PROJECT_FILE).read_bytes() == original
    assert Project.detect_version(folder) == 2
    result = migrate_legacy(folder, NEW_PASSWORD, NEW_PASSWORD)
    result.project.close()


def test_verification_failure_restores_original(legacy_project, monkeypatch):
    folder, _ = legacy_project
    original = (folder / PROJECT_FILE).read_bytes()
    def broken_open(*_args, **_kwargs):
        raise ValueError("doğrulama başarısız")
    monkeypatch.setattr(migration_module.Project, "open", classmethod(lambda cls, *a, **k: broken_open()))
    with pytest.raises(ValueError):
        migrate_legacy(folder, NEW_PASSWORD, NEW_PASSWORD)
    assert (folder / PROJECT_FILE).read_bytes() == original


def test_secure_delete_removes_file(tmp_path):
    target = tmp_path / "yedek.json"
    target.write_text("gizli-anahtar")
    secure_delete(target)
    assert not target.exists()


def test_short_password_rejected_before_any_write(legacy_project):
    folder, _ = legacy_project
    before = sorted(p.name for p in folder.iterdir())
    with pytest.raises(ValueError):
        migrate_legacy(folder, "kisa", "kisa")
    assert sorted(p.name for p in folder.iterdir()) == before


def test_tampered_legacy_surname_rejected(legacy_project):
    folder, _ = legacy_project
    data = json.loads((folder / PROJECT_FILE).read_text())
    data["group_surname_mappings"]["g1"]["h-soyad"] = "enc:" + base64.urlsafe_b64encode(b"0" * 40).decode()
    (folder / PROJECT_FILE).write_text(json.dumps(data))
    with pytest.raises(ValueError):
        migrate_legacy(folder, NEW_PASSWORD, NEW_PASSWORD)


def test_leftover_backup_detected(legacy_project):
    from siluet.migration import leftover_backup
    folder, _ = legacy_project
    assert leftover_backup(folder) is None
    result = migrate_legacy(folder, NEW_PASSWORD, NEW_PASSWORD)
    assert leftover_backup(folder) == result.backup_path
    secure_delete(result.backup_path)
    assert leftover_backup(folder) is None
    result.project.close()
