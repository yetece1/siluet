from pathlib import Path

from openpyxl import Workbook, load_workbook

from conftest import TEST_PASSWORD
from siluet.anonymizer import AnonymizationSession
from siluet.detector import detect_sections
from siluet.detector import classify_header
from siluet.project import Project, SCOPE_GROUP


def build_strict(path: Path):
    wb = Workbook(); ws = wb.active; ws.title = "Sheet0"
    ws.append(["GSM GÖRÜŞME SORGU SONUÇLARI"])
    ws.append(["SIRA NO", "AD", "BAZ (Numara)", "IMEI (Sorgulanan)", "Cihaz-IMEI No", "BİLİNMEYEN ALAN", "DURUM", "NOT", "MAHKEME"])
    ws.append([1, "ALİ", "BAZ-ANKARA-123", "490154203237518", "490154203237518356", "GİZLİ DEĞER", "GEÇERLİ", "Kayıt bulunamadı", "Ankara 3. Ağır Ceza Mahkemesi"])
    ws.append([2, "ECE", "BAZ-İZMİR-456", "4.90154203237518E+14", "ABC-IMEI-BOZUK", "12345", "ARANDI", "Kayıt bulunamadı 05321234567", "İzmir 2. Sulh Ceza Hakimliği"])
    wb.save(path)


def test_strict_all_data_columns_except_name_base_are_changed(tmp_path):
    source = tmp_path / "strict.xlsx"; build_strict(source)
    project = Project.create(tmp_path / "project", TEST_PASSWORD)
    output = AnonymizationSession(project).run([source], tmp_path / "out")[0]
    before, after = load_workbook(source)["Sheet0"], load_workbook(output)["Sheet0"]
    for row in (3, 4):
        assert after.cell(row, 2).value == before.cell(row, 2).value
        assert after.cell(row, 3).value == before.cell(row, 3).value
        assert after.cell(row, 1).value == before.cell(row, 1).value
        assert after.cell(row, 7).value == before.cell(row, 7).value
        for col in (4, 5, 6):
            assert after.cell(row, col).value != before.cell(row, col).value


def test_imei_header_variants_and_invalid_values_never_leak(tmp_path):
    source = tmp_path / "strict.xlsx"; build_strict(source)
    sections = detect_sections(load_workbook(source)["Sheet0"])
    assert sections[0].columns[4] == sections[0].columns[5] == "imei"
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    before, after = load_workbook(source)["Sheet0"], load_workbook(output)["Sheet0"]
    for coord in ("D3", "E3", "D4", "E4"):
        assert after[coord].value != before[coord].value


def test_system_literal_is_preserved_wherever_it_appears(tmp_path):
    source = tmp_path / "strict.xlsx"; build_strict(source)
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    before, after = load_workbook(source)["Sheet0"], load_workbook(output)["Sheet0"]
    assert after["H3"].value == "Kayıt bulunamadı"
    assert after["H4"].value == before["H4"].value


def test_system_literal_with_court_word_outside_table_is_preserved(tmp_path):
    source = tmp_path / "system-court.xlsx"
    wb = Workbook(); ws = wb.active
    ws.append(["Kayıt bulunamadı - Ankara Mahkemesi cevabı yoktur"])
    ws.append(["GSM GÖRÜŞME SORGU SONUÇLARI"])
    ws.append(["SIRA NO", "NUMARA", "BAZ"])
    ws.append([1, "05321234567", "BAZ-1"])
    wb.save(source)
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    assert load_workbook(output).active["A1"].value == "Kayıt bulunamadı - Ankara Mahkemesi cevabı yoktur"


def test_new_project_defaults_to_group_scoped_mapping(tmp_path):
    assert Project.create(tmp_path / "project", TEST_PASSWORD).mapping_scope == SCOPE_GROUP


def test_header_variants_preserve_name_base_date_duration_and_sizes():
    assert classify_header("İSİM") == "name"
    assert classify_header("BAZ") == "base"
    assert classify_header("İLETİŞİM TARİHİ") == "event_date"
    assert classify_header("TOPLAM BAĞLANTI SÜRESİ") == "duration"
    assert classify_header("GÖNDERİLEN VERİ BOYUTU (Byte)") == "byte_size"
    assert classify_header("İsim Soyisim (Numara)") == "full_name"
    assert classify_header("İsim Soyisim (  Numara)") == "full_name"


def test_court_information_is_completely_removed(tmp_path):
    source = tmp_path / "strict.xlsx"; build_strict(source)
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    ws = load_workbook(output)["Sheet0"]
    assert ws["I2"].value == "MAHKEME"
    assert ws["I3"].value in (None, "") and ws["I4"].value in (None, "")


def test_court_word_inside_base_data_does_not_trigger_metadata_removal(tmp_path):
    source = tmp_path / "strict.xlsx"; build_strict(source)
    wb = load_workbook(source); wb["Sheet0"]["C3"] = "ISPARTA ADLİYE MAHKEME BAZI-123"; wb.save(source)
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    assert load_workbook(output)["Sheet0"]["C3"].value == "ISPARTA ADLİYE MAHKEME BAZI-123"


def test_outputs_use_synthetic_values_without_marker_words(tmp_path):
    source = tmp_path / "strict.xlsx"; build_strict(source)
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    ws = load_workbook(output)["Sheet0"]
    payload = " ".join(str(c.value) for row in ws.iter_rows(min_row=3) for c in row if c.value is not None).upper()
    assert "ANON" not in payload and "ÖRNEK" not in payload and "TOKEN" not in payload
    assert ws["A3"].value == 1 and ws["G3"].value == "GEÇERLİ"


def test_prosecutor_information_is_completely_removed(tmp_path):
    source = tmp_path / "savcilik.xlsx"
    wb = Workbook(); ws = wb.active
    ws.append(["ABONE BİLGİLERİ"])
    ws.append(["AD", "SAVCILIK", "BAZ (Numara)"])
    ws.append(["ALİ", "Ankara Cumhuriyet Başsavcılığı", "BAZ-SAVCILIK-YANI-1"])
    wb.save(source)
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    target = load_workbook(output).active
    assert target["B3"].value in (None, "")
    assert target["C3"].value == "BAZ-SAVCILIK-YANI-1"


def test_merged_data_placeholders_do_not_cause_write_error(tmp_path):
    source = tmp_path / "merged.xlsx"
    wb = Workbook(); ws = wb.active
    ws.append(["GSM GÖRÜŞME SORGU SONUÇLARI"])
    ws.append(["NUMARA", "DİĞER NUMARA", "BAZ (Numara)"])
    ws.merge_cells("A3:B3"); ws["A3"] = "05321234567"; ws["C3"] = "BAZ-1"
    wb.save(source)
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    target = load_workbook(output).active
    assert str(target["A3"].value) != "05321234567"
    assert target["C3"].value == "BAZ-1"


def test_unrecognized_workbook_fails_closed_instead_of_copying_data(tmp_path):
    source = tmp_path / "unknown.xlsx"
    wb = Workbook(); ws = wb.active; ws.append(["Bilinmeyen", "Tablo"]); ws.append(["Gerçek kişi", "Gizli veri"]); wb.save(source)
    session = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD))
    try:
        session.run([source], tmp_path / "out")
        assert False, "unrecognized workbook was accepted"
    except RuntimeError as exc:
        assert "HTS" in str(exc) and not (tmp_path / "out" / "unknown.xlsx").exists()


def test_query_start_end_dates_stay_and_institution_never_replaces_them(tmp_path):
    source = tmp_path / "dates.xlsx"
    wb = Workbook(); ws = wb.active
    ws.append(["Talep Eden Makam", "Ankara Cumhuriyet Başsavcılığı"])
    ws.append(["GSM GÖRÜŞME SORGU SONUÇLARI"])
    ws.append(["SIRA NO", "SORGU BAŞLANGIÇ TARİHİ", "SORGU BİTİŞ TARİHİ", "BAZ"])
    ws.append([1, "07.06.2022 00:00:00", "07.06.2022 23:59:59", "BAZ-1"])
    wb.save(source)
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    target = load_workbook(output).active
    assert target["A4"].value == 1
    assert target["B4"].value == "07.06.2022 00:00:00"
    assert target["C4"].value == "07.06.2022 23:59:59"
    assert target["B1"].value in (None, "")
    assert "mahkeme" not in " ".join(str(c.value or "").casefold() for row in target.iter_rows() for c in row)


def test_specific_court_value_misdetected_as_header_is_still_removed_and_base_is_safe(tmp_path):
    source = tmp_path / "court-header.xlsx"
    wb = Workbook(); ws = wb.active
    ws.append(["ABONE BİLGİLERİ"])
    ws.append(["Talep Eden Makam", "Isparta 2. Ağır Ceza Mahkemesi"])
    ws.append(["SIRA NO", "DURUM", "BAZ"])
    ws.append([1, "GEÇERLİ", "ISPARTA ADLİYE YANI 1. CAD. MAH. BAZI"])
    wb.save(source)
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    target = load_workbook(output).active
    assert target["B2"].value in (None, "")
    assert target["A4"].value == 1 and target["B4"].value == "GEÇERLİ"
    assert target["C4"].value == "ISPARTA ADLİYE YANI 1. CAD. MAH. BAZI"
