import json

import pytest

from siluet import crypto_store
from siluet.crypto_store import (
    CorruptProjectError, WrongPasswordError, derive_key, open_sealed, read_header, seal, validate_new_password,
)

PASSWORD = "dogru-parola-123"


def _sealed(plaintext: bytes = b'{"gizli": "YILMAZ"}'):
    material = derive_key(PASSWORD)
    return material, seal(material, plaintext)


def _reopen(password: str, envelope: dict) -> bytes:
    salt, n, r, p = read_header(envelope)
    return open_sealed(derive_key(password, salt, n), envelope)


def test_roundtrip():
    _, envelope = _sealed()
    assert _reopen(PASSWORD, envelope) == b'{"gizli": "YILMAZ"}'


def test_wrong_password_raises():
    _, envelope = _sealed()
    with pytest.raises(WrongPasswordError):
        _reopen("yanlis-parola-123", envelope)


def test_tampered_ciphertext_raises():
    _, envelope = _sealed()
    raw = bytearray(crypto_store._b64d(envelope["ciphertext"]))
    raw[0] ^= 1
    envelope["ciphertext"] = crypto_store._b64e(bytes(raw))
    with pytest.raises(WrongPasswordError):
        _reopen(PASSWORD, envelope)


def test_tampered_kdf_header_raises():
    material, envelope = _sealed()
    envelope["kdf"]["r"] = 9
    with pytest.raises((WrongPasswordError, CorruptProjectError)):
        open_sealed(material, envelope)


def test_nonce_unique_per_seal():
    material = derive_key(PASSWORD)
    assert seal(material, b"x")["nonce"] != seal(material, b"x")["nonce"]


def test_header_contains_no_plaintext():
    _, envelope = _sealed()
    assert "YILMAZ" not in json.dumps(envelope)
    assert envelope["format"] == "hts-anonimlestirici" and envelope["version"] == 3
    assert envelope["cipher"] == "AES-256-GCM" and envelope["kdf"]["name"] == "scrypt"


def test_default_kdf_parameters(monkeypatch):
    monkeypatch.setattr(crypto_store, "SCRYPT_N", 2**17)
    monkeypatch.setattr(crypto_store, "_scrypt", lambda password, salt, n, r, p: b"k" * 32)
    material = derive_key(PASSWORD)
    assert (material.n, material.r, material.p, len(material.salt)) == (131072, 8, 1, 16)


def test_validate_new_password():
    with pytest.raises(ValueError):
        validate_new_password("123456789", "123456789")
    with pytest.raises(ValueError):
        validate_new_password("1234567890", "1234567891")
    assert validate_new_password("1234567890", "1234567890") is None


def test_unknown_version_corrupt():
    _, envelope = _sealed()
    envelope["version"] = 99
    with pytest.raises(CorruptProjectError):
        read_header(envelope)


def test_kdf_memory_cost_bounded():
    _, envelope = _sealed()
    envelope["kdf"].update({"n": 2**20, "r": 32, "p": 16})
    with pytest.raises(CorruptProjectError):
        read_header(envelope)
    envelope["kdf"].update({"n": 2**17, "r": 8, "p": 1})
    assert read_header(envelope)[1:] == (2**17, 8, 1)
