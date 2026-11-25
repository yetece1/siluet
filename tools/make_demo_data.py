"""Tamamen uydurma HTS demo verisi üretir (ekran görüntüleri ve deneme için).

- Telefonlar 0500 önekiyle üretilir (Türkiye'de abonelere atanmamış blok).
- T.C. numaraları kontrol haneleri bilinçli olarak geçersiz üretilir.
- Ad, soyad, adres ve baz adları uydurmadır; gerçek kişi veya yerle ilişkisi yoktur.

Kullanım: python tools/make_demo_data.py examples/demo
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

FIRST = ["ALİ", "ECE", "MERT", "ZEYNEP", "CAN", "DERYA", "EMRE", "SELİN", "BURAK", "İPEK", "KAAN", "NAZ"]
LAST = ["YILMAZ", "DEMİR", "KAYA", "ÇELİK", "ŞAHİN", "AKSOY", "ARSLAN", "KORKMAZ", "ÖZTÜRK", "AYDIN"]
BAZ = ["ÖRNEK-MERKEZ-{:03d}", "DENEME-SAHİL-{:03d}", "YAPAY-SANAYİ-{:03d}", "KURGU-ÜNİVERSİTE-{:03d}"]
HEADER_FILL = PatternFill("solid", fgColor="DDE6F0")
BOLD = Font(bold=True)


def fake_phone(rng: random.Random) -> str:
    return f"0500 {rng.randint(0, 999):03d} {rng.randint(0, 99):02d} {rng.randint(0, 99):02d}"


def fake_tckn(rng: random.Random) -> str:
    digits = [rng.randint(1, 9)] + [rng.randint(0, 9) for _ in range(8)]
    d10 = (sum(digits[0:9:2]) * 7 - sum(digits[1:8:2])) % 10
    d11 = (sum(digits) + d10) % 10
    return "".join(map(str, digits)) + str(d10) + str((d11 + 1) % 10)  # bilinçli geçersiz


def _title(ws, text: str) -> None:
    ws.append([text])
    ws.cell(ws.max_row, 1).font = BOLD


def _header(ws, columns: list[str]) -> None:
    ws.append(columns)
    for cell in ws[ws.max_row]:
        cell.font = BOLD
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")


def build_case(folder: Path, case_no: int, rng: random.Random) -> None:
    subject = {"phone": fake_phone(rng), "first": rng.choice(FIRST), "last": rng.choice(LAST), "tc": fake_tckn(rng)}
    contacts = [(fake_phone(rng), f"{rng.choice(FIRST)} {rng.choice(LAST)}") for _ in range(8)]
    start = datetime(2026, 3, 1, 8, 0) + timedelta(days=case_no * 3)
    dossier = f"DOSYA NO: 2099/{900 + case_no}"

    def common(ws, title: str) -> None:
        ws.title = "Sheet0"
        ws.append([dossier])
        ws.append([title])
        ws.cell(2, 1).font = Font(bold=True, size=13)
        ws.append([])
        _title(ws, "ABONE BİLGİLERİ")
        _header(ws, ["SIRA NO", "NUMARA", "AD", "SOYAD", "TC KİMLİK NO", "ADRES", "DOGUM TARİHİ", "DOGUM YERİ"])
        ws.append([1, subject["phone"], subject["first"], subject["last"], subject["tc"],
                   f"Kurgu Mah. {case_no}. Sok. No:{rng.randint(1, 60)}", f"0{rng.randint(1, 9)}.0{rng.randint(1, 9)}.19{rng.randint(70, 99)}",
                   "ÖRNEKİL"])
        ws.append([])
        _title(ws, "GSM GÖRÜŞME SORGU SONUÇLARI")
        _header(ws, ["SIRA NO", "NUMARA", "TİP", "DİĞER NUMARA", "İsim Soyisim (Diğer Numara)", "TARİH", "SÜRE", "BAZ (Numara)"])
        moment = start
        for index in range(1, 41):
            other, name = rng.choice(contacts)
            moment += timedelta(minutes=rng.randint(7, 240))
            ws.append([index, subject["phone"], rng.choice(["ARAYAN", "ARANAN", "SMS"]), other, name,
                       moment.strftime("%d.%m.%Y %H:%M:%S"), rng.randint(0, 900),
                       rng.choice(BAZ).format(rng.randint(1, 40))])

    main = Workbook()
    ws = main.active
    common(ws, "HTS SORGU SONUÇLARI (ANA BAZ)")
    ws.append([])
    _title(ws, "İNTERNET BAĞLANTI (GPRS) İLETİŞİM SORGU SONUÇLARI")
    _header(ws, ["SIRA NO", "NUMARA", "KAYNAK IP", "HEDEF IP", "TARİH", "BAZ (Numara)"])
    moment = start
    for index in range(1, 21):
        moment += timedelta(minutes=rng.randint(15, 300))
        ws.append([index, subject["phone"], f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
                   f"192.0.2.{rng.randint(1, 254)}", moment.strftime("%d.%m.%Y %H:%M:%S"),
                   rng.choice(BAZ).format(rng.randint(1, 40))])
    for column, width in zip("ABCDEFGH", (9, 18, 14, 18, 30, 20, 8, 26)):
        ws.column_dimensions[column].width = width
    main.save(folder / f"demo-{case_no}-a.xlsx")

    counter = Workbook()
    ws = counter.active
    common(ws, "HTS SORGU SONUÇLARI (KARŞI BAZ)")
    for column, width in zip("ABCDEFGH", (9, 18, 14, 18, 30, 20, 8, 26)):
        ws.column_dimensions[column].width = width
    counter.save(folder / f"demo-{case_no}-b.xlsx")


def main() -> None:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/demo")
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(2099)
    for case_no in range(1, 4):
        build_case(folder, case_no, rng)
    print(f"Demo verisi yazıldı: {folder}")


if __name__ == "__main__":
    main()
