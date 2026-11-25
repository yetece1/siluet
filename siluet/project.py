from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import crypto_store
from .crypto_store import KeyMaterial, WrongPasswordError


PROJECT_FILE = "hts-projesi.json"
LOCK_FILE = ".hts-proje-kilidi"
PAYLOAD_VERSION = 3

# Bu süreçte açık olan projeler (normcase yol -> Project). İkinci açılışı engeller.
_OPEN_PROJECTS: dict[str, "Project"] = {}


class LegacyProjectError(ValueError):
    """Proje eski (parolasız) biçimde; önce taşınması gerekir."""


class ProjectLockedError(RuntimeError):
    """Proje başka bir pencerede veya süreçte açık."""


# Klasör (normcase) -> kilidi tutan açık dosya tanımlayıcısı.
_LOCK_HANDLES: dict[str, int] = {}


def _os_try_lock(fd: int) -> bool:
    """İşletim sistemi düzeyinde, süreç ölünce kendiliğinden bırakılan özel kilit."""
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _os_unlock(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def _acquire_lock(folder: Path) -> None:
    key = os.path.normcase(str(folder))
    if key in _OPEN_PROJECTS or key in _LOCK_HANDLES:
        raise ProjectLockedError("Bu proje zaten açık.")
    lock = folder / LOCK_FILE
    for _attempt in range(5):
        fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        if not _os_try_lock(fd):
            os.close(fd)
            raise ProjectLockedError("Bu proje başka bir pencerede veya bilgisayarda açık.")
        # Başka bir süreç biz kilitlerken dosyayı silip yeniden oluşturduysa yeni dosyayla tekrar dene.
        try:
            same = os.path.samestat(os.fstat(fd), os.stat(lock))
        except FileNotFoundError:
            same = False
        if not same:
            _os_unlock(fd)
            os.close(fd)
            continue
        info = json.dumps({"pid": os.getpid(), "host": socket.gethostname()}).encode("utf-8")
        if os.name == "nt":
            # Windows'ta kilitli ilk bayt yazılamaz; bilgi kilit baytından sonra yazılır.
            os.lseek(fd, 1, os.SEEK_SET)
            os.write(fd, info)
        else:
            os.ftruncate(fd, 0)
            os.write(fd, info)
        _LOCK_HANDLES[key] = fd
        return
    raise ProjectLockedError("Proje kilidi alınamadı.")


def _release_lock(folder: Path) -> None:
    key = os.path.normcase(str(folder))
    fd = _LOCK_HANDLES.pop(key, None)
    if fd is None:
        return
    lock = folder / LOCK_FILE
    if os.name != "nt":
        # POSIX'te kilit hâlâ bizdeyken silinir; bekleyen süreç samestat ile yeni dosyaya geçer.
        lock.unlink(missing_ok=True)
    _os_unlock(fd)
    os.close(fd)
    if os.name == "nt":
        try:
            lock.unlink()
        except OSError:
            pass  # başka bir süreç dosyayı açtıysa kalır; içerik kilit değildir
ROLE_MAIN = "main"
ROLE_COUNTER = "counter"
SCOPE_PROJECT = "project"
SCOPE_GROUP = "group"


@dataclass
class FileEntry:
    path: str
    role: str
    sheets: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.path = str(Path(self.path).resolve())
        if self.role not in {ROLE_MAIN, ROLE_COUNTER}:
            raise ValueError("Geçersiz dosya türü")


@dataclass
class FileGroup:
    group_id: str
    name: str
    files: list[FileEntry] = field(default_factory=list)

    @classmethod
    def create(cls, name: str) -> "FileGroup":
        clean = name.strip()
        if not clean:
            raise ValueError("Grup adı boş olamaz")
        return cls(uuid.uuid4().hex, clean)


@dataclass
class Project:
    path: Path
    project_id: str
    secret: bytes = field(repr=False)
    surname_mappings: dict[str, str] = field(default_factory=dict)
    mapping_state: dict[str, dict[str, str]] = field(default_factory=dict)
    field_overrides: dict[str, str] = field(default_factory=dict)
    groups: list[FileGroup] = field(default_factory=list)
    mapping_scope: str = SCOPE_GROUP
    group_surname_mappings: dict[str, dict[str, str]] = field(default_factory=dict)
    group_mapping_state: dict[str, dict[str, dict[str, str]]] = field(default_factory=dict)

    _material: KeyMaterial | None = field(default=None, repr=False, compare=False)
    _locked: bool = field(default=False, repr=False, compare=False)

    @classmethod
    def create(cls, path: Path, password: str) -> "Project":
        crypto_store.validate_new_password(password, password)
        path = Path(path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        if (path / PROJECT_FILE).exists():
            raise FileExistsError("Seçilen klasörde zaten bir HTS projesi var")
        _acquire_lock(path)
        project = cls(path, secrets.token_hex(8), secrets.token_bytes(32))
        project._locked = True
        _OPEN_PROJECTS[os.path.normcase(str(path))] = project
        try:
            project._material = crypto_store.derive_key(password)
            project.save()
        except BaseException:
            project.close()
            raise
        return project

    @staticmethod
    def detect_version(path: Path) -> int | None:
        target = Path(path) / PROJECT_FILE
        if not target.is_file():
            return None
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise crypto_store.CorruptProjectError("Proje dosyası okunamadı.") from exc
        if crypto_store.is_envelope(data):
            version = data.get("version")
            if not isinstance(version, int):
                raise crypto_store.CorruptProjectError("Proje dosyası bozuk.")
            return version
        if isinstance(data, dict) and data.get("version") in {1, 2}:
            return int(data["version"])
        raise crypto_store.CorruptProjectError("Tanınmayan proje dosyası.")

    @classmethod
    def open(cls, path: Path, password: str) -> "Project":
        path = Path(path).resolve()
        version = cls.detect_version(path)
        if version is None:
            raise FileNotFoundError("Bu klasörde HTS projesi yok")
        if version in {1, 2}:
            raise LegacyProjectError("Proje eski biçimde. Önce parola belirlenerek taşınmalı.")
        envelope = json.loads((path / PROJECT_FILE).read_text(encoding="utf-8"))
        salt, n, r, p = crypto_store.read_header(envelope)
        material = crypto_store.derive_key(password, salt, n, r, p)
        plaintext = crypto_store.open_sealed(material, envelope)
        _acquire_lock(path)
        try:
            project = cls.from_payload(path, json.loads(plaintext.decode("utf-8")))
        except BaseException:
            _release_lock(path)
            raise
        project._material = material
        project._locked = True
        _OPEN_PROJECTS[os.path.normcase(str(path))] = project
        return project

    @classmethod
    def from_payload(cls, path: Path, data: dict) -> "Project":
        """Şifresi çözülmüş (ya da taşıma sırasında okunmuş) içerikten proje kurar."""
        if data.get("payload_version") != PAYLOAD_VERSION:
            raise crypto_store.CorruptProjectError("Desteklenmeyen proje içeriği.")
        secret = base64.b64decode(data["internal_key"].encode("ascii"))
        if len(secret) != 32:
            raise ValueError("Proje anahtar verisi geçersiz")
        groups = [FileGroup(x["group_id"], x["name"], [FileEntry(**f) for f in x.get("files", [])]) for x in data.get("groups", [])]
        project = cls(
            path, data["project_id"], secret, dict(data.get("surname_mappings", {})),
            {ns: dict(values) for ns, values in data.get("mapping_state", {}).items()},
            dict(data.get("field_overrides", {})), groups, data.get("mapping_scope", SCOPE_GROUP),
            {gid: dict(values) for gid, values in data.get("group_surname_mappings", {}).items()},
            {gid: {ns: dict(values) for ns, values in state.items()} for gid, state in data.get("group_mapping_state", {}).items()},
        )
        project._validate()
        return project

    def close(self) -> None:
        key = os.path.normcase(str(self.path))
        if _OPEN_PROJECTS.get(key) is self:
            del _OPEN_PROJECTS[key]
        if self._locked:
            _release_lock(self.path)
            self._locked = False
        self._material = None

    def __enter__(self) -> "Project":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def change_password(self, old: str, new: str, confirm: str) -> None:
        if self._material is None:
            raise RuntimeError("Proje kapalı")
        check = crypto_store.derive_key(old, self._material.salt, self._material.n, self._material.r, self._material.p)
        if not secrets.compare_digest(check.key, self._material.key):
            raise WrongPasswordError("Mevcut parola yanlış.")
        crypto_store.validate_new_password(new, confirm)
        previous = self._material
        self._material = crypto_store.derive_key(new)
        try:
            self.save()
        except BaseException:
            self._material = previous
            raise

    @classmethod
    def open_or_create(cls, path: Path, password: str) -> "Project":
        return cls.open(path, password) if (Path(path) / PROJECT_FILE).exists() else cls.create(path, password)

    def _validate(self) -> None:
        if self.mapping_scope not in {SCOPE_PROJECT, SCOPE_GROUP}:
            raise ValueError("Eşleme kapsamı geçersiz")
        seen: set[str] = set()
        for group in self.groups:
            for entry in group.files:
                key = os.path.normcase(str(Path(entry.path).resolve()))
                if key in seen:
                    raise ValueError("Aynı dosya projeye birden fazla eklenmiş")
                seen.add(key)

    def add_group(self, name: str) -> FileGroup:
        if any(g.name.casefold() == name.strip().casefold() for g in self.groups):
            raise ValueError("Bu grup adı zaten kullanılıyor")
        group = FileGroup.create(name)
        self.groups.append(group)
        self.save()
        return group

    def get_group(self, group_id: str) -> FileGroup:
        for group in self.groups:
            if group.group_id == group_id:
                return group
        raise KeyError("Dosya grubu bulunamadı")

    def rename_group(self, group_id: str, name: str) -> None:
        clean = name.strip()
        if not clean or any(g.group_id != group_id and g.name.casefold() == clean.casefold() for g in self.groups):
            raise ValueError("Grup adı boş veya kullanımda")
        self.get_group(group_id).name = clean
        self.save()

    def delete_group(self, group_id: str) -> None:
        self.groups = [g for g in self.groups if g.group_id != group_id]
        self.group_mapping_state.pop(group_id, None)
        self.group_surname_mappings.pop(group_id, None)
        self.save()

    def add_file(self, group_id: str, path: Path, role: str, sheets: list[str] | None = None) -> FileEntry:
        resolved = str(path.resolve())
        if any(os.path.normcase(f.path) == os.path.normcase(resolved) for g in self.groups for f in g.files):
            raise ValueError("Aynı dosya projeye iki kez eklenemez")
        entry = FileEntry(resolved, role, list(sheets or []))
        self.get_group(group_id).files.append(entry)
        self.save()
        return entry

    def add_auto_groups(self, groups) -> int:
        """Add pre-inspected automatic groups and persist exactly once."""
        existing = {os.path.normcase(f.path) for g in self.groups for f in g.files}
        pending: list[tuple[FileGroup, list[FileEntry]]] = []
        used_names = {g.name.casefold() for g in self.groups}
        next_number = 1
        for auto_group in groups:
            entries: list[FileEntry] = []
            for profile in auto_group.profiles:
                resolved = os.path.normcase(str(profile.path.resolve()))
                if resolved in existing:
                    continue
                entries.append(FileEntry(str(profile.path), profile.role, profile.sheets))
                existing.add(resolved)
            if entries:
                while f"otomatik {next_number:03d}" in used_names:
                    next_number += 1
                group = FileGroup.create(f"Otomatik {next_number:03d}")
                used_names.add(group.name.casefold())
                next_number += 1
                pending.append((group, entries))
        original_count = len(self.groups)
        original_scope = self.mapping_scope
        try:
            for group, entries in pending:
                group.files.extend(entries)
                self.groups.append(group)
            if pending:
                self.mapping_scope = SCOPE_GROUP
                self.save()
        except Exception:
            del self.groups[original_count:]
            self.mapping_scope = original_scope
            raise
        return sum(len(entries) for _, entries in pending)

    def remove_file(self, path: Path) -> None:
        resolved = os.path.normcase(str(path.resolve()))
        for group in self.groups:
            group.files = [f for f in group.files if os.path.normcase(f.path) != resolved]
        self.save()

    def find_file(self, path: Path) -> tuple[FileGroup, FileEntry]:
        resolved = os.path.normcase(str(path.resolve()))
        for group in self.groups:
            for entry in group.files:
                if os.path.normcase(entry.path) == resolved:
                    return group, entry
        raise KeyError("Dosya projede bulunamadı")

    def move_file(self, path: Path, target_group_id: str) -> None:
        source_group, entry = self.find_file(path)
        target = self.get_group(target_group_id)
        source_group.files.remove(entry)
        target.files.append(entry)
        self.save()

    def set_file_role(self, path: Path, role: str) -> None:
        _, entry = self.find_file(path)
        if role not in {ROLE_MAIN, ROLE_COUNTER}:
            raise ValueError("Geçersiz dosya türü")
        entry.role = role
        self.save()

    def mapping_context(self, group_id: str) -> tuple[bytes, dict[str, str], dict[str, dict[str, str]]]:
        if self.mapping_scope == SCOPE_PROJECT:
            return self.secret, self.surname_mappings, self.mapping_state
        derived = hmac.new(self.secret, b"group-scope:" + group_id.encode("ascii"), hashlib.sha256).digest()
        return derived, self.group_surname_mappings.setdefault(group_id, {}), self.group_mapping_state.setdefault(group_id, {})

    def update_mapping_context(self, group_id: str, surnames: dict[str, str], state: dict[str, dict[str, str]]) -> None:
        if self.mapping_scope == SCOPE_PROJECT:
            self.surname_mappings, self.mapping_state = surnames, state
        else:
            self.group_surname_mappings[group_id] = surnames
            self.group_mapping_state[group_id] = state

    def payload(self) -> dict:
        return {
            "payload_version": PAYLOAD_VERSION, "project_id": self.project_id,
            "internal_key": base64.b64encode(self.secret).decode("ascii"),
            "surname_mappings": self.surname_mappings,
            "mapping_state": self.mapping_state, "field_overrides": self.field_overrides,
            "groups": [asdict(g) for g in self.groups], "mapping_scope": self.mapping_scope,
            "group_surname_mappings": self.group_surname_mappings,
            "group_mapping_state": self.group_mapping_state,
        }

    def save(self) -> None:
        if self._material is None:
            raise RuntimeError("Proje kapalı; kaydedilemez")
        self._validate()
        plaintext = json.dumps(self.payload(), ensure_ascii=False).encode("utf-8")
        envelope = crypto_store.seal(self._material, plaintext)
        write_atomic_json(self.path / PROJECT_FILE, envelope)


def write_atomic_json(target: Path, data: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".hts-proje-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
