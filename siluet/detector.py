from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable

from openpyxl.worksheet.worksheet import Worksheet

from .normalization import fold
from .normalization import digits


SECTION_PHRASES = (
    "abone bilgileri",
    "gsm gorusme sorgu sonuclari",
    "sabit telefon gorusme sorgu sonuclari",
    "uluslararasi gorusme sorgu sonuclari",
    "mesaj bilgileri mms ve sms sorgu sonuclari",
    "internet baglanti gprs iletisim sorgu sonuclari",
    "internet baglanti wap iletisim sorgu sonuclari",
    "sth gorusme sorgu sonuclari",
    "ipdr", "cgnat", "konum kayitlari", "baz hareket", "imei sorgu", "imsi sorgu",
    "numara eslestirme", "abone gecmisi", "hat devir", "cihaz sim eslesme",
    "internet erisim", "mesaj yonlendirme",
)

ALIASES: dict[str, tuple[str, ...]] = {
    "base": ("baz", "baz bilgisi", "baz numara", "baz numarasi", "baz istasyonu", "cell id baz"),
    "phone": ("sorgulanan no", "diger no", "numara", "diger numara", "telefon", "telefon no", "gsm", "arayan", "aranan", "a numara", "b numara"),
    "tc": ("tc kimlik no", "tc kimlik numarasi", "t c kimlik no", "tckn", "kimlik numarasi diger numara"),
    "name": ("ad", "adi", "isim", "ismi"),
    "surname": ("soyad", "soyadi"),
    "full_name": ("isim soyisim diger numara", "isim soyisim", "ad soyad", "adi soyadi"),
    "mother": ("anne adi",),
    "father": ("baba adi",),
    "address": ("adres", "abone adresi", "ikamet adresi"),
    "birth_place": ("dogum yeri",),
    "birth_date": ("dogum tarihi",),
    "personal_district": ("ilce",),
    "personal_city": ("il",),
    "imei": ("imei", "imei no",),
    "imsi": ("imsi", "imsi no", "cihaz seri numarasi"),
    "iccid": ("iccid", "sim kart seri numarasi", "sim seri no"),
    "mac": ("mac", "mac adresi", "mac address"),
    "ip": ("kaynak ip", "hedef ip", "ip adresi", "ip"),
    "url": ("erisilen sayfa", "url", "web adresi"),
    "gateway": ("basl gateway", "sonl gateway", "baslangic gateway", "sonlandirma gateway"),
    "switch": ("basl santral", "sonl santral", "baslangic santral", "sonlandirma santral"),
    "pin": ("pin no", "pin"),
    "institution": ("talep eden makam", "mahkeme", "savcilik", "kurum", "birim"),
    "file_number": ("dosya no", "esas no", "karar no", "sorusturma no", "yazi no", "evrak no"),
    "free_text": ("mesaj metni", "mesaj icerigi", "sms icerigi", "mms icerigi", "aciklama", "notlar", "serbest aciklama"),
    "location": ("gps", "gps koordinati", "cihaz koordinati", "abone konumu", "kisi konumu", "konum aciklamasi"),
    "serial": ("sira no", "sira", "kayit no"),
    "preserve_type": ("tip", "data tip", "mesaj icerik tipi"),
    "event_date": ("tarih", "tarih saat", "abone sorgu araligi", "abone baslangic", "abone bitis"),
    "duration": ("sure", "arama suresi", "baglanti suresi"),
    "status": ("durum",),
    "operator": ("operator",),
    "byte_size": ("mesaj boyutu byte", "gonderme boyutu byte", "indirme boyutu byte"),
}

SYSTEM_LITERALS = ("kayit bulunamadi", "veri bulunamadi", "sonuc bulunamadi")


@dataclass
class Section:
    title: str
    title_row: int
    header_row: int | None = None
    end_row: int | None = None
    columns: dict[int, str] = field(default_factory=dict)
    raw_headers: dict[int, str] = field(default_factory=dict)


def is_section_title(value: object) -> bool:
    normalized = fold(value)
    if not normalized:
        return False
    for phrase in SECTION_PHRASES:
        if phrase == normalized:
            return True
        # Sütun başlıklarındaki "IMEI (Sorgulanan)" gibi ifadeler bölüm
        # başlığı değildir. Kısmi eşleşme yalnız sonuç başlıklarında kullanılır.
        if phrase in normalized and "sonuc" in normalized:
            return True
    return False


def classify_header(value: object, section_title: str = "") -> str | None:
    normalized = fold(value)
    if not normalized:
        return None
    if normalized in SYSTEM_LITERALS:
        return "preserve"
    if "talep eden makam" in normalized:
        return "institution"
    # Tam eşleşmeden önce en ayırt edici teknik başlıkları yakala.
    # Örn. "IMEI (Sorgulanan)", "Cihaz IMEI No", "Kaynak-IP Adresi".
    token_rules = (
        ("imei", "imei"), ("imsi", "imsi"), ("iccid", "iccid"),
        ("mac", "mac"), ("gateway", "gateway"), ("santral", "switch"),
        ("pin", "pin"), ("tc kimlik", "tc"), ("tckn", "tc"),
        ("dogum tarihi", "birth_date"), ("dogum yeri", "birth_place"),
        ("isim soyisim", "full_name"), ("ad soyad", "full_name"),
        ("soyad", "surname"), ("anne adi", "mother"), ("baba adi", "father"),
        ("adres", "address"), ("mahkeme", "court"), ("hakimlik", "court"),
        ("adliye", "court"), ("bassavcilik", "court"), ("savcilik", "court"),
        ("dosya no", "file_number"), ("esas no", "file_number"), ("karar no", "file_number"),
    )
    for token, category in token_rules:
        if token in normalized:
            if category == "address" and ("baz" in normalized or "baz" in fold(section_title)):
                return "base"
            return category
    if "tarih" in normalized:
        return "event_date"
    if re.search(r"\bsure(?:si)?\b", normalized):
        return "duration"
    if "boyut" in normalized and any(token in normalized for token in ("gonder", "indir", "mesaj", "byte")):
        return "byte_size"
    section_norm = fold(section_title)
    if ("baz hareket" in section_norm or "baz istasyon" in section_norm) and any(token in normalized for token in ("adres", "konum", "koordinat", "enlem", "boylam", "ilce", "cell", "lac", "tac", "cgi", "site", "sektor", "azimut", "frekans", "operator")):
        return "base"
    if len(normalized.split()) <= 8 and "baz" in normalized and any(token in normalized for token in ("numara", "adres", "konum", "kod", "adi", "enlem", "boylam", "il", "ilce", "operator")):
        return "base"
    for category, aliases in ALIASES.items():
        if normalized in aliases:
            if category in {"address", "personal_city", "personal_district"} and "baz" in fold(section_title):
                return "base"
            return category
    if any(token in normalized for token in ("cell id", "cellid", "lac", "tac", "cgi", "ecgi", "site id", "azimut", "sektor", "baz enlem", "baz boylam")):
        return "base"
    # Güvenli varsayılan: açıkça hassas görünen yeni başlıkları koruma.
    sensitive_tokens = {
        "pasaport": "identifier", "sicil": "identifier", "personel": "identifier",
        "iban": "identifier", "hesap": "identifier", "email": "identifier",
        "e posta": "identifier", "plaka": "identifier", "kullanici": "identifier",
    }
    for token, category in sensitive_tokens.items():
        if token in normalized:
            return category
    return None


def _header_score(values: Iterable[object], section_title: str) -> int:
    return sum(classify_header(value, section_title) is not None for value in values)


def infer_category(values: Iterable[object]) -> str | None:
    samples = [str(v).strip() for v in values if v not in (None, "")][:30]
    if not samples:
        return None
    total = len(samples)
    if sum(bool(re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?", x)) for x in samples) / total >= .7:
        return "ip"
    lengths = [len(digits(x)) for x in samples]
    if sum(n == 11 for n in lengths) / total >= .8:
        return "phone"
    if sum(n in (14, 15) for n in lengths) / total >= .8:
        return "imei"
    if sum(n in (15, 16) for n in lengths) / total >= .8:
        return "imsi"
    if sum("@" in x and "." in x for x in samples) / total >= .7:
        return "free_text"
    return None


def detect_sections(ws: Worksheet) -> list[Section]:
    sections: list[Section] = []
    for row in ws.iter_rows():
        candidates = [str(c.value) for c in row if c.value is not None and is_section_title(c.value)]
        if candidates:
            sections.append(Section(title=candidates[0], title_row=row[0].row))
    # Başlıksız ama tablo biçimli dosyalar için sanal bölüm.
    if not sections:
        sections = [Section(title="TANIMSIZ BOLUM", title_row=0)]
    for index, section in enumerate(sections):
        boundary = sections[index + 1].title_row - 1 if index + 1 < len(sections) else ws.max_row
        best_row, best_score = None, 0
        start = max(1, section.title_row + 1)
        for row_no in range(start, min(boundary, start + 12) + 1):
            values = [ws.cell(row_no, col).value for col in range(1, ws.max_column + 1)]
            score = _header_score(values, section.title)
            if score > best_score:
                best_row, best_score = row_no, score
        # Tek tanınan hücre çoğunlukla sorgu üst bilgisi/etiketidir; tablo başlığı
        # saymak için en az iki alan gerekir.
        section.header_row = best_row if best_score >= 2 else None
        section.end_row = boundary
        if section.header_row:
            for col in range(1, ws.max_column + 1):
                raw = ws.cell(section.header_row, col).value
                category = classify_header(raw, section.title)
                if raw is not None:
                    section.raw_headers[col] = str(raw)
                if category:
                    section.columns[col] = category
            for col in section.raw_headers:
                if col not in section.columns:
                    inferred = infer_category(ws.cell(row, col).value for row in range(section.header_row + 1, boundary + 1))
                    # Veri sütunları sessizce korunmaz. İçerik türü belirlenemezse
                    # biçim koruyan genel anonimleştirmeye yönlendirilir.
                    section.columns[col] = inferred or "generic"
    return sections
