from __future__ import annotations

from copy import copy
from pathlib import Path

import pytest
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


@pytest.fixture
def sample_pair(tmp_path: Path):
    def build(path: Path, reversed_rows=False):
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet0"
        ws.column_dimensions["A"].width = 14
        ws.column_dimensions["J"].width = 46
        ws.row_dimensions[1].height = 27
        ws.merge_cells("A1:J1")
        ws["A1"] = "ABONE BİLGİLERİ"
        ws["A1"].font = Font(bold=True, color="FFFFFF")
        ws["A1"].fill = PatternFill("solid", fgColor="C00000")
        headers = ["SIRA NO", "NUMARA", "AD", "SOYAD", "TC KİMLİK NO", "ADRES", "DOGUM TARİHİ", "DOGUM YERİ", "ANNE ADI", "BABA ADI"]
        ws.append(headers)
        rows = [
            [1, "0532 123 45 67", "ALİ", "YILMAZ", "12345678901", "Örnek Mah. 1", "01.01.1980", "ANKARA", "AYŞE", "MEHMET"],
            [2, "0542 987 65 43", "ECE", "DEMİR", "98765432109", "Deneme Cad. 2", "02.02.1990", "İZMİR", "FATMA", "HASAN"],
            [3, None, "", "", None, "Kayıt bulunamadı", None, None, None, None],
        ]
        if reversed_rows:
            rows[:2] = reversed(rows[:2])
        for values in rows: ws.append(values)
        ws.merge_cells("A6:J6")
        ws["A6"] = "GSM GÖRÜŞME SORGU SONUÇLARI"
        ws["A6"].fill = copy(ws["A1"].fill)
        ws.append(["SIRA NO", "NUMARA", "TİP", "DİĞER NUMARA", "TARİH", "SÜRE", "İsim Soyisim ( Diğer Numara)", "DURUM", "IMEI", "BAZ (Numara)"])
        thin = Side(style="thin", color="000000")
        for cell in ws[7]:
            cell.font = Font(bold=True)
            cell.border = Border(bottom=thin)
            cell.alignment = Alignment(horizontal="center")
        ws.append([1, "0532 123 45 67", "Giden", "0542 987 65 43", "01.03.2026 10:00", 60, "ECE DEMİR", "Tamam", "490154203237518", "1234-ANKARA/MERKEZ 39.9,32.8"])
        ws.append([2, "0542 987 65 43", "Gelen", "0532 123 45 67", "01.03.2026 10:01", 30, "ALİ YILMAZ", "Tamam", "356938035643809", "5678-İZMİR/KONAK 38.4,27.1"])
        ws.append([3, "Kayıt bulunamadı", None, None, None, None, None, None, None, "Kayıt bulunamadı"])
        ws.merge_cells("A11:J11")
        ws["A11"] = "İNTERNET BAĞLANTI (GPRS) İLETİŞİM SORGU SONUÇLARI"
        ws.append(["SIRA NO", "NUMARA", "TİP", "TARİH", "SÜRE", "IMEI", "KAYNAK IP", "GÖNDERME BOYUTU (Byte)", "İNDİRME BOYUTU (Byte)", "BAZ (Numara)"])
        ws.append([1, "0532 123 45 67", "GPRS", "01.03.2026 11:00", 10, "490154203237518", "8.8.8.8", 100, 200, "1234-ANKARA/MERKEZ 39.9,32.8"])
        wb.save(path)
    a, b = tmp_path / "ana.xlsx", tmp_path / "karsi.xlsx"
    build(a)
    build(b, reversed_rows=True)
    return a, b


TEST_PASSWORD = "test-parolasi-2026"


@pytest.fixture(autouse=True)
def _fast_scrypt(monkeypatch):
    """Testlerde scrypt maliyetini düşürür; üretim değeri test_crypto_store'da ayrıca doğrulanır."""
    try:
        from siluet import crypto_store
    except ImportError:
        return
    monkeypatch.setattr(crypto_store, "SCRYPT_N", 2**10)


@pytest.fixture(autouse=True)
def _release_project_locks():
    yield
    try:
        from siluet import project as project_module
    except ImportError:
        return
    for opened in list(getattr(project_module, "_OPEN_PROJECTS", {}).values()):
        opened.close()
