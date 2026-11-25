from __future__ import annotations

import re
import unicodedata
import ipaddress
from decimal import Decimal, InvalidOperation


TR_MAP = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"})


def fold(value: object) -> str:
    text = str(value or "").translate(TR_MAP).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def digits(value: object) -> str:
    return "".join(re.findall(r"\d", str(value or "")))


def restore_case(source: str, target: str) -> str:
    if source.isupper():
        return target.upper()
    if source.islower():
        return target.lower()
    if source.istitle():
        return target.title()
    return target


def replace_digits_by_positions(source: str, replacement_digits: str) -> str:
    positions = [i for i, c in enumerate(source) if c.isdigit()]
    if len(positions) != len(replacement_digits):
        raise ValueError("Rakam sayisi eslesmiyor")
    chars = list(source)
    for pos, digit in zip(positions, replacement_digits):
        chars[pos] = digit
    return "".join(chars)


PHONE_CANDIDATE_RE = re.compile(r"(?:\+?90[\s().-]*)?0?5\d{2}(?:[\s().-]*\d){7}")
IPV4_CANDIDATE_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?(?![\d.])")
MAC_CANDIDATE_RE = re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])")
URL_CANDIDATE_RE = re.compile(r"(?i)https?://[^\s<>]+")


def excel_scalar_text(value: object) -> str:
    """Excel sayısal hücrelerini bilimsel gösterim eklemeden metne çevirir."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(Decimal(str(value)), "f")
    text = str(value or "").strip()
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?[Ee][+-]?\d+", text):
        try:
            return format(Decimal(text), "f").split(".", 1)[0]
        except InvalidOperation:
            return text
    return text


def normalize_phone_cell(value: object) -> tuple[str, bool]:
    """Telefon sütununda tek kaydı seçer; birleşmiş/tekrarlanmış artıkları atar."""
    text = excel_scalar_text(value)
    matches = list(PHONE_CANDIDATE_RE.finditer(text))
    if matches:
        first = matches[0].group(0).strip()
        return first, first != text or len(matches) > 1
    all_digits = digits(text)
    if len(all_digits) <= 15:
        return text, False
    # Ayraçsız birleşmiş telefonlarda ilk kayıt, Türkiye numara başlangıcına
    # göre belirlenir. Bu kural sadece telefon olarak sınıflanmış hücrede çalışır.
    if all_digits.startswith("90") and len(all_digits) >= 12:
        size = 12
    elif all_digits.startswith("0") and len(all_digits) >= 11:
        size = 11
    elif all_digits.startswith("5") and len(all_digits) >= 10:
        size = 10
    else:
        size = next((n for n in (11, 10, 12, 13) if len(all_digits) >= n and len(all_digits) % n == 0), min(15, len(all_digits)))
    return all_digits[:size], True


def _first_numeric_record(text: str, allowed_lengths: tuple[int, ...]) -> tuple[str, bool]:
    raw_digits = digits(text)
    if len(raw_digits) in allowed_lengths:
        return text, False
    runs = re.findall(r"\d+", text)
    for run in runs:
        if len(run) in allowed_lengths:
            return run, run != text
    for size in allowed_lengths:
        if len(raw_digits) > size and len(raw_digits) % size == 0:
            return raw_digits[:size], True
    if len(raw_digits) > max(allowed_lengths):
        return raw_digits[:max(allowed_lengths)], True
    return text, False


def _collapse_exact_duplicate(text: str) -> tuple[str, bool]:
    stripped = text.strip()
    if len(stripped) >= 2 and len(stripped) % 2 == 0:
        half = len(stripped) // 2
        if stripped[:half] == stripped[half:]:
            return stripped[:half], True
    parts = re.split(r"\s*[|;/]+\s*", stripped)
    if len(parts) >= 2 and parts and all(part == parts[0] for part in parts):
        return parts[0], True
    return text, False


def normalize_classified_value(value: object, category: str) -> tuple[object, bool]:
    """Sütun türüne göre ham Excel değerini tek, doğrulanabilir kayda indirger."""
    if value is None:
        return value, False
    text = excel_scalar_text(value)
    if category == "phone":
        return normalize_phone_cell(value)
    if category == "tc":
        return _first_numeric_record(text, (11,))
    if category == "imei":
        return _first_numeric_record(text, (15, 14))
    if category == "imsi":
        return _first_numeric_record(text, (15, 16))
    if category == "iccid":
        return _first_numeric_record(text, (20, 19, 18, 21, 22))
    if category == "mac":
        found = MAC_CANDIDATE_RE.search(text)
        return (found.group(0), found.group(0) != text) if found else _collapse_exact_duplicate(text)
    if category == "ip":
        found = IPV4_CANDIDATE_RE.search(text)
        if found:
            candidate = found.group(0)
            host = candidate.rsplit(":", 1)[0] if candidate.count(":") == 1 else candidate
            try:
                ipaddress.ip_address(host)
                return candidate, candidate != text
            except ValueError:
                return _collapse_exact_duplicate(text)
        # IPv6 veya IPv6:port için boşlukla ayrılmış ilk geçerli parçayı seç.
        for token in re.split(r"[\s,;|]+", text):
            candidate = token.strip("[]")
            try:
                ipaddress.ip_address(candidate)
                return token, token != text
            except ValueError:
                continue
        return _collapse_exact_duplicate(text)
    if category == "url":
        found = URL_CANDIDATE_RE.search(text)
        return (found.group(0), found.group(0) != text) if found else _collapse_exact_duplicate(text)
    if category in {"pin", "gateway", "switch", "identifier", "file_number"}:
        return _collapse_exact_duplicate(text)
    return value, False
