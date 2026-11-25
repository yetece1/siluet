"""Tamamen yapay ana baz ve karşı baz test dosyaları üretir."""
from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill


def build(path: Path, reverse: bool = False) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet0"
    ws.merge_cells("A1:J1")
    ws["A1"] = "ABONE BİLGİLERİ"
    ws["A1"].font = Font(bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor="C00000")
    ws.append(["SIRA NO", "NUMARA", "AD", "SOYAD", "TC KİMLİK NO", "ADRES", "DOGUM TARİHİ", "DOGUM YERİ", "ANNE ADI", "BABA ADI"])
    rows = [
        [1, "0532 000 11 22", "ALİ", "YILMAZ", "12345678901", "Tamamen Yapay Mah. 1", "01.01.1980", "ÖRNEKİL", "AYŞE", "MEHMET"],
        [2, "0542 000 33 44", "ECE", "DEMİR", "98765432109", "Tamamen Yapay Cad. 2", "02.02.1990", "DENEMEİL", "FATMA", "HASAN"],
    ]
    for row in reversed(rows) if reverse else rows:
        ws.append(row)
    ws.merge_cells("A5:J5")
    ws["A5"] = "GSM GÖRÜŞME SORGU SONUÇLARI"
    ws.append(["SIRA NO", "NUMARA", "TİP", "DİĞER NUMARA", "TARİH", "SÜRE", "İsim Soyisim ( Diğer Numara)", "DURUM", "IMEI", "BAZ (Numara)"])
    ws.append([1, "0532 000 11 22", "Giden", "0542 000 33 44", "01.03.2026 10:00", 60, "ECE DEMİR", "Tamam", "490154203237518", "TEST-BAZ / ÖRNEK KONUM 0,0"])
    wb.save(path)


def main() -> None:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "ornekler")
    output.mkdir(parents=True, exist_ok=True)
    build(output / "sahte_ana_baz.xlsx")
    build(output / "sahte_karsi_baz.xlsx", reverse=True)
    print(f"İki yapay dosya üretildi: {output}")


if __name__ == "__main__":
    main()
