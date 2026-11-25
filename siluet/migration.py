"""Eski (v1/v2, parolasız) projeleri parolalı v3 biçimine güvenle taşır.

Sıra: parola doğrulama -> eski dosyayı okuma -> yedek -> v3 yazma -> yeniden
açarak doğrulama. Doğrulama başarısızsa orijinal dosya geri yüklenir.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import crypto_store
from .mapping_store import MappingStore
from .project import PAYLOAD_VERSION, PROJECT_FILE, Project, write_atomic_json

BACKUP_NAME = "hts-projesi.v2-yedek.json"


@dataclass
class MigrationResult:
    project: Project
    backup_path: Path
    dropped_namespaces: list[str] = field(default_factory=list)


def _legacy_unprotect(secret: bytes, value: str) -> str:
    if not isinstance(value, str) or not value.startswith("enc:"):
        raise ValueError("Eski proje eşleme deposu korumasız veya geçersiz")
    blob = base64.urlsafe_b64decode(value[4:].encode("ascii"))
    nonce, tag, encrypted = blob[:16], blob[16:32], blob[32:]
    expected = hmac.new(secret, b"project-tag" + nonce + encrypted, hashlib.sha256).digest()[:16]
    if len(nonce) != 16 or not hmac.compare_digest(tag, expected):
        raise ValueError("Eski proje eşleme deposu bütünlük doğrulaması başarısız")
    stream, counter = b"", 0
    while len(stream) < len(encrypted):
        stream += hmac.new(secret, b"project-store" + nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(a ^ b for a, b in zip(encrypted, stream)).decode("utf-8")


def _drop_retired(state: dict, dropped: set[str]) -> dict:
    kept = {}
    for namespace, values in state.items():
        if namespace in MappingStore.retired_namespaces:
            dropped.add(namespace)
        else:
            kept[namespace] = dict(values)
    return kept


def legacy_payload(data: dict) -> tuple[dict, list[str]]:
    """v1/v2 içeriğini v3 şifreli bölüm içeriğine çevirir."""
    if data.get("version") not in {1, 2}:
        raise crypto_store.CorruptProjectError("Taşınacak eski proje sürümü tanınmadı.")
    secret = base64.urlsafe_b64decode(data["internal_key"].encode("ascii"))
    if len(secret) != 32:
        raise ValueError("Proje anahtar verisi geçersiz")
    dropped: set[str] = set()
    payload = {
        "payload_version": PAYLOAD_VERSION, "project_id": data["project_id"],
        "internal_key": base64.b64encode(secret).decode("ascii"),
        "surname_mappings": {k: _legacy_unprotect(secret, v) for k, v in data.get("surname_mappings", {}).items()},
        "mapping_state": _drop_retired(data.get("mapping_state", {}), dropped),
        "field_overrides": dict(data.get("field_overrides", {})),
        "groups": data.get("groups", []), "mapping_scope": data.get("mapping_scope", "group"),
        "group_surname_mappings": {gid: {k: _legacy_unprotect(secret, v) for k, v in values.items()}
                                   for gid, values in data.get("group_surname_mappings", {}).items()},
        "group_mapping_state": {gid: _drop_retired(state, dropped)
                                for gid, state in data.get("group_mapping_state", {}).items()},
    }
    return payload, sorted(dropped)


def _write_bytes_atomic(target: Path, raw: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".hts-proje-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def migrate_legacy(path: Path, new_password: str, confirm: str) -> MigrationResult:
    crypto_store.validate_new_password(new_password, confirm)
    folder = Path(path).resolve()
    if Project.detect_version(folder) not in {1, 2}:
        raise crypto_store.CorruptProjectError("Bu proje taşınacak eski biçimde değil.")
    target = folder / PROJECT_FILE
    original = target.read_bytes()
    payload, dropped = legacy_payload(json.loads(original.decode("utf-8")))
    Project.from_payload(folder, payload)  # yazmadan önce içerik doğrulaması

    backup = folder / BACKUP_NAME
    _write_bytes_atomic(backup, original)
    material = crypto_store.derive_key(new_password)
    envelope = crypto_store.seal(material, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    write_atomic_json(target, envelope)
    try:
        project = Project.open(folder, new_password)
    except BaseException:
        _write_bytes_atomic(target, original)
        raise
    return MigrationResult(project, backup, dropped)


def leftover_backup(folder: Path) -> Path | None:
    """Taşımadan kalmış düz metin anahtarlı yedek varsa yolunu döndürür."""
    candidate = Path(folder) / BACKUP_NAME
    return candidate if candidate.is_file() else None


def secure_delete(path: Path) -> None:
    """Dosyanın içeriğini rastgele baytlarla ezip siler.

    En iyi çaba: USB bellek, SSD ve kopyala-yaz dosya sistemlerinde eski blokların
    fiziksel olarak silindiği garanti edilemez.
    """
    path = Path(path)
    size = path.stat().st_size
    with path.open("r+b") as handle:
        remaining = size
        while remaining > 0:
            chunk = min(remaining, 1024 * 1024)
            handle.write(secrets.token_bytes(chunk))
            remaining -= chunk
        handle.flush(); os.fsync(handle.fileno())
    path.unlink()
