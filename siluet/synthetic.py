from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .mapping_store import MappingStore
from .normalization import restore_case


TYPES = ("Arama", "Aranma", "Mesaj", "İnternet", "Yönlendirme")
STATUSES = ("Geçerli", "Tamamlandı", "Cevapsız", "Başarılı", "Sonlandırıldı")
OPERATORS = ("Kuzey Telekom", "Mavi İletişim", "Anadolu Mobil", "Kent Haberleşme")
CITIES = ("Ankara", "İzmir", "Bursa", "Konya", "Samsun", "Eskişehir", "Kayseri", "Antalya")
STREETS = ("Güven", "Çınar", "Işık", "Ufuk", "Barış", "Pınar", "Güneş", "Deniz")
INSTITUTIONS = ("Merkez Cumhuriyet Başsavcılığı", "Kuzey 3. Ağır Ceza Mahkemesi", "Anadolu 2. Sulh Ceza Hakimliği", "Batı Adliyesi Yazı İşleri Müdürlüğü")


class SyntheticFactory:
    """Etiket kullanmadan, HMAC kaynağından gerçekçi ve tekrarlanabilir sahte değer üretir."""

    def __init__(self, store: MappingStore): self.store = store

    def _number(self, namespace: str, value: object, minimum: int, maximum: int) -> int:
        raw = self.store.digest(namespace, str(value)); return minimum + int.from_bytes(raw[:8], "big") % (maximum - minimum + 1)

    def choice(self, namespace: str, value: object, choices: tuple[str, ...]) -> str:
        candidate = choices[self._number(namespace, value, 0, len(choices) - 1)]
        if str(value).strip().casefold() == candidate.casefold(): candidate = choices[(choices.index(candidate) + 1) % len(choices)]
        return restore_case(str(value), candidate)

    def serial(self, value):
        number = self._number("serial", value, 1, 999999)
        return number if isinstance(value, (int, float)) and not isinstance(value, bool) else str(number)

    def duration(self, value):
        text = str(value).strip()
        if re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", text):
            seconds = self._number("duration", text, 1, 86399); return f"{seconds//3600:02d}:{seconds%3600//60:02d}:{seconds%60:02d}"
        number = self._number("duration", text, 1, 7200)
        return number if isinstance(value, (int, float)) and not isinstance(value, bool) else str(number)

    def byte_size(self, value):
        number = self._number("byte-size", value, 32, 50_000_000)
        return number if isinstance(value, (int, float)) and not isinstance(value, bool) else str(number)

    def date_value(self, value):
        offset = self._number("event-date", value, 1, 730)
        if isinstance(value, datetime): return value + timedelta(days=offset, minutes=self._number("event-minute", value, 1, 1439))
        if isinstance(value, date): return value + timedelta(days=offset)
        text = str(value).strip()
        for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try: return (datetime.strptime(text, fmt) + timedelta(days=offset)).strftime(fmt)
            except ValueError: continue
        return self.store.formatted_identifier(text, "event-date")

    def address(self, value):
        raw = self.store.digest("address-realistic", str(value)); street = STREETS[raw[0] % len(STREETS)]; city = CITIES[raw[1] % len(CITIES)]
        return f"{street} Mah. {1 + raw[2] % 90}. Sk. No:{1 + raw[3] % 120} D:{1 + raw[4] % 30} {city}"

    def place(self, value): return self.choice("place", value, CITIES)
    def institution(self, value): return self.choice("institution", value, INSTITUTIONS)
    def status(self, value): return self.choice("status", value, STATUSES)
    def call_type(self, value): return self.choice("call-type", value, TYPES)
    def operator(self, value): return self.choice("operator", value, OPERATORS)

