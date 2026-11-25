from __future__ import annotations

import hashlib
import hmac
import ipaddress
from urllib.parse import urlsplit, urlunsplit
from collections import defaultdict

from .normalization import digits, fold, replace_digits_by_positions, restore_case


ARTIFICIAL_SURNAMES = (
    "Arıner", "Bilginer", "Dengiz", "Erkutay", "Günsel", "Işıner", "Özünal", "Sezginel",
    "Tanırel", "Ulueren", "Yalınel", "Yücer", "Akgüner", "Dorukel", "Esenay", "Kutuner",
)
ARTIFICIAL_NAMES = ("Deniz", "Ekin", "Deren", "Umut", "Aren", "Ilgın", "Öykü", "Çağın")


TR_CLASS_DIGITS = "23458"


def split_phone(source_digits: str) -> tuple[str, str, str]:
    """Numarayı (korunan önek, sınıf hanesi, yenilenecek gövde) olarak ayırır.

    Yalnız Türkiye ülke/trunk öneki ve ulusal numaranın ilk hanesi korunur.
    """
    for prefix in ("0090", "90", "0"):
        rest = source_digits[len(prefix):]
        if source_digits.startswith(prefix) and len(rest) == 10 and rest[0] != "0":
            return prefix, rest[0], rest[1:]
    return "", source_digits[:1], source_digits[1:]


class MappingStore:
    """Gerçek değerleri yalnızca işlem belleğinde tutan, HMAC tabanlı eşleme deposu."""

    def __init__(self, secret: str | bytes, surname_state: dict[str, str] | None = None, persistent_state: dict[str, dict[str, str]] | None = None):
        if not secret or len(secret) < 12:
            raise ValueError("Dahili proje anahtarı geçersiz")
        self.key = secret.encode("utf-8") if isinstance(secret, str) else secret
        self.maps: dict[str, dict[str, str]] = defaultdict(dict)
        self.reverse: dict[str, dict[str, str]] = defaultdict(dict)
        self.surname_map: dict[str, str] = {}
        self.surname_state = surname_state if surname_state is not None else {}
        self.persistent_state = persistent_state if persistent_state is not None else {}
        self.persistent_reverse = {}
        for namespace, values in self.persistent_state.items():
            reverse = {value: key for key, value in values.items()}
            if len(reverse) != len(values):
                raise ValueError(f"{namespace} eşleme deposunda çakışma bulundu")
            self.persistent_reverse[namespace] = reverse

    def digest(self, namespace: str, normalized: str, counter: int = 0) -> bytes:
        message = f"{namespace}\0{normalized}\0{counter}".encode("utf-8")
        return hmac.new(self.key, message, hashlib.sha256).digest()

    def _unique(self, namespace: str, source: str, factory) -> str:
        source_key = self.source_hash(namespace, source)
        persisted = self.persistent_state.get(namespace, {}).get(source_key)
        if persisted is not None and persisted != source:
            self.maps[namespace][source] = persisted
            self.reverse[namespace][persisted] = source
            return persisted
        if persisted == source:
            self.persistent_state[namespace].pop(source_key, None)
            self.persistent_reverse.get(namespace, {}).pop(persisted, None)
        existing = self.maps[namespace].get(source)
        if existing is not None:
            return existing
        counter = 0
        while True:
            candidate = factory(self.digest(namespace, source, counter))
            owner = self.reverse[namespace].get(candidate)
            persisted_owner = self.persistent_reverse.get(namespace, {}).get(candidate)
            if candidate != source and (owner is None or owner == source) and (persisted_owner is None or persisted_owner == source_key):
                self.maps[namespace][source] = candidate
                self.reverse[namespace][candidate] = source
                self.persistent_state.setdefault(namespace, {})[source_key] = candidate
                self.persistent_reverse.setdefault(namespace, {})[candidate] = source_key
                return candidate
            counter += 1
            if counter > 100_000:
                raise RuntimeError(f"{namespace} eşlemesi için çakışma çözülemedi")

    def prepare_surnames(self, surnames: list[str]) -> None:
        originals: dict[str, str] = {}
        for value in surnames:
            normalized = fold(value)
            if normalized:
                originals.setdefault(normalized, value.strip())
        unmapped = {k: v for k, v in originals.items() if self.source_hash("surname", k) not in self.surname_state}
        ordered = sorted(unmapped, key=lambda x: self.digest("surname-order", x))
        if len(ordered) >= 2 and not self.surname_state:
            shift = 1 + int.from_bytes(self.digest("surname-shift", str(len(ordered)))[:4], "big") % (len(ordered) - 1)
            targets = ordered[shift:] + ordered[:shift]
            self.surname_map = {src: unmapped[target] for src, target in zip(ordered, targets)}
        else:
            used = {fold(x) for x in self.surname_state.values()}
            self.surname_map = {}
            for source in ordered:
                candidates = [x for x in ARTIFICIAL_SURNAMES if fold(x) != source and fold(x) not in used]
                if not candidates:
                    candidates = [f"Soyad{self.digest('surname-fallback', source).hex()[:6].upper()}"]
                idx = int.from_bytes(self.digest("surname-fallback", source)[:4], "big") % len(candidates)
                self.surname_map[source] = candidates[idx]
                used.add(fold(candidates[idx]))
        for source, target in self.surname_map.items():
            self.surname_state[self.source_hash("surname", source)] = target

    def source_hash(self, namespace: str, normalized: str) -> str:
        return hmac.new(self.key, f"source\0{namespace}\0{normalized}".encode("utf-8"), hashlib.sha256).hexdigest()

    def surname(self, value: str) -> str:
        normalized = fold(value)
        target = self.surname_state.get(self.source_hash("surname", normalized)) or self.surname_map.get(normalized)
        if target is None:
            candidates = [x for x in ARTIFICIAL_SURNAMES if fold(x) != normalized]
            idx = int.from_bytes(self.digest("surname-fallback", normalized)[:4], "big") % len(candidates)
            target = candidates[idx]
            self.surname_map[normalized] = target
            self.surname_state[self.source_hash("surname", normalized)] = target
        return restore_case(value, target)

    def related_name(self, value: str, role: str) -> str:
        source = fold(value)
        def factory(raw: bytes) -> str:
            return restore_case(value, ARTIFICIAL_NAMES[int.from_bytes(raw[:4], "big") % len(ARTIFICIAL_NAMES)])
        return self._unique(f"name:{role}", source, factory)

    retired_namespaces = ("phone", "phone-tr", "tc")

    def phone(self, value: str) -> str:
        source_digits = digits(value)
        if len(source_digits) < 5:
            return value
        prefix, class_digit, body = split_phone(source_digits)
        national = class_digit + body
        if prefix or (len(national) == 10 and class_digit in TR_CLASS_DIGITS):
            # Aynı abone 0532…, 90532…, +90 532…, 532… biçimlerinde yazılabilir;
            # eşleme ulusal numara üzerinden yapılır ki ilişki biçimden bağımsız korunsun.
            namespace, source_key = "phone-tr", national
        else:
            namespace, source_key = "phone", source_digits
        def factory(raw: bytes) -> str:
            number = int.from_bytes(raw, "big") % (10 ** len(body))
            return class_digit + str(number).zfill(len(body))
        # TR dışı numaralarda önek boştur; kaynak ile aday aynı uzunlukta karşılaştırılır.
        return replace_digits_by_positions(str(value), prefix + self._unique(namespace, source_key, factory))

    @staticmethod
    def _valid_tckn(value: str) -> bool:
        if len(value) != 11 or not value.isdigit() or value[0] == "0":
            return False
        d = [int(x) for x in value]
        return ((sum(d[0:9:2]) * 7 - sum(d[1:8:2])) % 10 == d[9] and sum(d[:10]) % 10 == d[10])

    def tc(self, value: str) -> str:
        source_digits = digits(value)
        if len(source_digits) != 11:
            return value
        def factory(raw: bytes) -> str:
            first = str(1 + raw[0] % 9)
            rest = str(int.from_bytes(raw[1:], "big") % (10 ** 10)).zfill(10)
            candidate = first + rest
            if self._valid_tckn(candidate):
                # Üretilen numara hiçbir gerçek vatandaşa ait olamasın diye geçersizliğe zorlanır.
                candidate = candidate[:10] + str((int(candidate[10]) + 1) % 10)
            return candidate
        mapped = self._unique("tc", source_digits, factory)
        return replace_digits_by_positions(str(value), mapped)

    @staticmethod
    def _luhn_digit(first14: str) -> str:
        total = 0
        for i, ch in enumerate(first14):
            n = int(ch) * (2 if i % 2 == 0 else 1)
            total += n // 10 + n % 10
        return str((10 - total % 10) % 10)

    def imei(self, value: str) -> str:
        source_digits = digits(value)
        if len(source_digits) not in (14, 15):
            return value
        core = source_digits[:14]
        def factory(raw: bytes) -> str:
            number = str(int.from_bytes(raw, "big") % (10 ** 14)).zfill(14)
            if number[0] == "0":
                number = "8" + number[1:]
            return number
        mapped_core = self._unique("imei-core", core, factory)
        mapped = mapped_core + self._luhn_digit(mapped_core) if len(source_digits) == 15 else mapped_core
        return replace_digits_by_positions(str(value), mapped)

    def numeric_identifier(self, value: str, namespace: str) -> str:
        source_digits = digits(value)
        if not source_digits:
            return self.token(value, namespace)
        def factory(raw: bytes) -> str:
            number = str(int.from_bytes(raw, "big") % (10 ** len(source_digits))).zfill(len(source_digits))
            return ("8" + number[1:]) if number.startswith("0") and not source_digits.startswith("0") else number
        mapped = self._unique(namespace, source_digits, factory)
        return replace_digits_by_positions(str(value), mapped)

    def formatted_identifier(self, value: str, namespace: str) -> str:
        source_digits = digits(value)
        mapped = self.numeric_identifier(source_digits, namespace)
        iterator = iter(mapped)
        return "".join(next(iterator) if char.isdigit() else char for char in str(value))

    def ip(self, value: str) -> str:
        source = str(value).strip()
        try:
            address = ipaddress.ip_address(source)
        except ValueError:
            return value
        if address.version == 4:
            networks = ("192.0.2.", "198.51.100.", "203.0.113.")
            def factory(raw: bytes) -> str:
                return networks[raw[0] % 3] + str(1 + raw[1] % 254)
            return self._unique("ipv4", source, factory)
        def factory6(raw: bytes) -> str:
            suffix = int.from_bytes(raw[:12], "big")
            return str(ipaddress.IPv6Address((0x20010DB8 << 96) | suffix))
        return self._unique("ipv6", source.lower(), factory6)

    def token(self, value: str, namespace: str, prefix: str = "ANON") -> str:
        source = fold(value)
        def factory(raw: bytes) -> str:
            letters = "ABCDEFGHJKLMNPRSTUVYZ"
            digits_pool = "0123456789"
            output = []
            index = 0
            for char in str(value):
                byte = raw[index % len(raw)]; index += 1
                if char.isalpha():
                    replacement = letters[byte % len(letters)]
                    output.append(replacement.lower() if char.islower() else replacement)
                elif char.isdigit(): output.append(digits_pool[byte % 10])
                else: output.append(char)
            candidate = "".join(output)
            return candidate or letters[raw[0] % len(letters)]
        return self._unique(namespace, source, factory)

    def url(self, value: str, mode: str = "domain") -> str:
        if mode == "clear":
            return ""
        if mode == "all":
            return "https://" + self.token(value, "url-host").lower() + ".test"
        try:
            parsed = urlsplit(value)
            if parsed.scheme and parsed.netloc:
                host = self.token(parsed.hostname or value, "url-host").lower() + ".test"
                token = self.token(parsed.path or value, "url-path").lower()
                return urlunsplit((parsed.scheme, host, f"/{token.strip('/')}", "", ""))
        except ValueError:
            return "https://" + self.token(value, "url-host").lower() + ".test"
        return "https://" + self.token(value, "url-host").lower() + ".test"
