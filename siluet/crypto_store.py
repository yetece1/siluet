"""Parola tabanlı proje zarfı: scrypt ile anahtar türetme, AES-256-GCM ile şifreleme.

Zarfın düz metin kısmında yalnız biçim bilgisi, KDF parametreleri, salt ve nonce
bulunur. Bu başlık AEAD ek verisi olarak bağlandığından üzerinde oynanırsa çözme
başarısız olur.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

# Proje dosyası biçim kimliği; v2.0 öncesi adla uyumluluk için değiştirilmez.
FORMAT = "hts-anonimlestirici"
VERSION = 3
CIPHER = "AES-256-GCM"
MIN_PASSWORD_LENGTH = 10
SCRYPT_N = 2**17
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
NONCE_BYTES = 12
# Bozuk ya da kötü niyetli başlıkların aşırı bellek/süre tüketmesini önler.
MAX_SCRYPT_N = 2**20
MAX_SCRYPT_MEMORY = 256 * 1024 * 1024  # scrypt belleği ≈ 128·n·r bayt
MAX_SCRYPT_P = 4


class WrongPasswordError(ValueError):
    """Parola yanlış veya şifreli içerik değiştirilmiş."""


class CorruptProjectError(ValueError):
    """Proje zarfının yapısı okunamıyor."""


@dataclass(frozen=True)
class KeyMaterial:
    key: bytes
    salt: bytes
    n: int
    r: int
    p: int


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def validate_new_password(password: str, confirm: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Parola en az {MIN_PASSWORD_LENGTH} karakter olmalı.")
    if password != confirm:
        raise ValueError("Parolalar eşleşmiyor.")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(password.encode("utf-8"))


def derive_key(password: str, salt: bytes | None = None, n: int | None = None,
               r: int = SCRYPT_R, p: int = SCRYPT_P) -> KeyMaterial:
    if not password:
        raise WrongPasswordError("Parola boş olamaz.")
    salt = salt if salt is not None else os.urandom(SALT_BYTES)
    n = n if n is not None else SCRYPT_N
    return KeyMaterial(_scrypt(password, salt, n, r, p), salt, n, r, p)


def _header(material_or_kdf) -> dict:
    if isinstance(material_or_kdf, KeyMaterial):
        kdf = {"name": "scrypt", "n": material_or_kdf.n, "r": material_or_kdf.r,
               "p": material_or_kdf.p, "salt": _b64e(material_or_kdf.salt)}
    else:
        kdf = material_or_kdf
    return {"format": FORMAT, "version": VERSION, "kdf": kdf, "cipher": CIPHER}


def _aad(header: dict) -> bytes:
    return json.dumps(header, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def seal(material: KeyMaterial, plaintext: bytes) -> dict:
    header = _header(material)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(material.key).encrypt(nonce, plaintext, _aad(header))
    return {**header, "nonce": _b64e(nonce), "ciphertext": _b64e(ciphertext)}


def is_envelope(data: object) -> bool:
    return isinstance(data, dict) and data.get("format") == FORMAT


def read_header(envelope: dict) -> tuple[bytes, int, int, int]:
    try:
        if envelope.get("format") != FORMAT or envelope.get("version") != VERSION or envelope.get("cipher") != CIPHER:
            raise CorruptProjectError("Desteklenmeyen proje dosyası sürümü.")
        kdf = envelope["kdf"]
        if kdf.get("name") != "scrypt":
            raise CorruptProjectError("Desteklenmeyen anahtar türetme yöntemi.")
        n, r, p = int(kdf["n"]), int(kdf["r"]), int(kdf["p"])
        salt = _b64d(kdf["salt"])
    except CorruptProjectError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise CorruptProjectError("Proje dosyası bozuk.") from exc
    if (not (2 <= n <= MAX_SCRYPT_N and n & (n - 1) == 0) or not (1 <= r <= 32) or not (1 <= p <= MAX_SCRYPT_P)
            or 128 * n * r > MAX_SCRYPT_MEMORY or len(salt) < 16):
        raise CorruptProjectError("Proje dosyasının şifreleme parametreleri geçersiz.")
    return salt, n, r, p


def open_sealed(material: KeyMaterial, envelope: dict) -> bytes:
    read_header(envelope)
    try:
        nonce = _b64d(envelope["nonce"])
        ciphertext = _b64d(envelope["ciphertext"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CorruptProjectError("Proje dosyası bozuk.") from exc
    header = _header(envelope["kdf"])
    try:
        return AESGCM(material.key).decrypt(nonce, ciphertext, _aad(header))
    except InvalidTag as exc:
        raise WrongPasswordError("Parola yanlış veya proje dosyası değiştirilmiş.") from exc
