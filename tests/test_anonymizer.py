from __future__ import annotations

import threading

from openpyxl import load_workbook
from openpyxl.comments import Comment

from conftest import TEST_PASSWORD
from siluet.anonymizer import AnonymizationSession
from siluet.mapping_store import MappingStore
from siluet.project import Project
from siluet.sanitizer import sanitize_text
from siluet.text_anonymizer import TextAnonymizer
from siluet.normalization import digits, normalize_classified_value, normalize_phone_cell
from siluet.validators import workbook_structure


def run_pair(sample_pair, tmp_path):
    out = tmp_path / "out"
    project = Project.create(tmp_path / "project", TEST_PASSWORD)
    session = AnonymizationSession(project)
    outputs = session.run(list(sample_pair), out)
    return outputs, session


def test_direct_session_outputs_keep_source_names_and_no_reports(sample_pair, tmp_path):
    outputs, _ = run_pair(sample_pair, tmp_path)
    assert [path.name for path in outputs] == [path.name for path in sample_pair]
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == ["ana.xlsx", "karsi.xlsx"]


def test_format_sheet_rows_and_order_preserved(sample_pair, tmp_path):
    outputs, session = run_pair(sample_pair, tmp_path)
    for source, target in zip(sample_pair, outputs):
        assert workbook_structure(source) == workbook_structure(target)
        assert load_workbook(source).sheetnames == load_workbook(target).sheetnames == ["Sheet0"]
    assert session.report.integrity["structure_preserved"]
    assert session.report.integrity["row_order_preserved"]


def test_base_cells_unchanged(sample_pair, tmp_path):
    outputs, _ = run_pair(sample_pair, tmp_path)
    for source, target in zip(sample_pair, outputs):
        a, b = load_workbook(source)["Sheet0"], load_workbook(target)["Sheet0"]
        assert [a[f"J{x}"].value for x in (8, 9, 10, 13)] == [b[f"J{x}"].value for x in (8, 9, 10, 13)]


def test_phone_tc_fully_replaced_and_cross_file_consistency(sample_pair, tmp_path):
    outputs, _ = run_pair(sample_pair, tmp_path)
    source = load_workbook(sample_pair[0])["Sheet0"]
    out_a, out_b = (load_workbook(x)["Sheet0"] for x in outputs)
    def digits(v): return "".join(c for c in str(v) if c.isdigit())
    for coord in ("B3", "B4", "B8", "D8"):
        before, after = digits(source[coord].value), digits(out_a[coord].value)
        assert len(before) == len(after)
        assert before[:2] == after[:2]
        assert before[2:] != after[2:]
        # Hane konumu benzerliğinin istatistiksel denetimi sabit anahtarla test_number_mapping'de yapılır;
        # burada proje anahtarı rastgele olduğundan tek hücrelik eşik kararsız olurdu.
    before, after = digits(source["E3"].value), digits(out_a["E3"].value)
    assert len(after) == 11 and before[:10] != after[:10]
    assert out_a["B3"].value == out_b["B4"].value
    assert out_a["B4"].value == out_b["B3"].value


def test_surname_bijection_no_selfmap_and_name_preserved(sample_pair, tmp_path):
    outputs, _ = run_pair(sample_pair, tmp_path)
    source, target = load_workbook(sample_pair[0])["Sheet0"], load_workbook(outputs[0])["Sheet0"]
    originals = {source["D3"].value, source["D4"].value}
    mapped = {target["D3"].value, target["D4"].value}
    assert len(mapped) == len(originals) == 2
    assert target["D3"].value != source["D3"].value
    assert target["D4"].value != source["D4"].value
    assert target["C3"].value == source["C3"].value
    assert target["C4"].value == source["C4"].value
    assert target["G8"].value.split()[0] == source["G8"].value.split()[0]


def test_counter_base_full_name_header_variant_stays_natural(sample_pair, tmp_path):
    source = sample_pair[1]
    wb = load_workbook(source); ws = wb["Sheet0"]
    ws["G7"] = "İsim Soyisim (  Numara)"; wb.save(source)
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    before, after = load_workbook(source)["Sheet0"], load_workbook(output)["Sheet0"]
    assert after["G8"].value.split()[0] == before["G8"].value.split()[0]
    assert after["G8"].value != before["G8"].value


def test_imei_ip_full_change_and_consistency(sample_pair, tmp_path):
    outputs, _ = run_pair(sample_pair, tmp_path)
    source, target = load_workbook(sample_pair[0])["Sheet0"], load_workbook(outputs[0])["Sheet0"]
    assert target["I8"].value != source["I8"].value
    assert len(target["I8"].value) == len(source["I8"].value) == 15
    assert target["F13"].value == target["I8"].value
    assert target["G13"].value != source["G13"].value
    assert target["G13"].value.startswith(("192.0.2.", "198.51.100.", "203.0.113."))


def test_blank_and_system_literals_preserved(sample_pair, tmp_path):
    outputs, _ = run_pair(sample_pair, tmp_path)
    source, target = load_workbook(sample_pair[0])["Sheet0"], load_workbook(outputs[0])["Sheet0"]
    for coord in ("B5", "C5", "D5", "E5", "F5", "B10", "J10"):
        assert target[coord].value == source[coord].value


def test_verbatim_fields_are_not_changed_by_final_text_cleanup(sample_pair, tmp_path):
    source = sample_pair[0]
    wb = load_workbook(source); ws = wb["Sheet0"]
    ws["C8"] = "  Giden  "; ws["E8"] = " 01.03.2026 10:00 "; ws["F8"] = " 60 "
    ws["C10"] = "Kayıt bulunamadı   "; wb.save(source)
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    target = load_workbook(output)["Sheet0"]
    assert target["C8"].value == "  Giden  "
    assert target["E8"].value == " 01.03.2026 10:00 "
    assert target["F8"].value == " 60 "
    assert target["C10"].value == "Kayıt bulunamadı   "


def test_headers_and_unclassified_system_literals_remain_byte_for_byte(sample_pair, tmp_path):
    source = sample_pair[0]
    wb = load_workbook(source); ws = wb["Sheet0"]
    ws["C7"] = "  TİP  "; ws["A14"] = "  Kayıt bulunamadı   "; wb.save(source)
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    target = load_workbook(output)["Sheet0"]
    assert target["C7"].value == "  TİP  "
    assert target["A14"].value == "  Kayıt bulunamadı   "


def test_hidden_metadata_comments_and_hyperlinks_are_removed(sample_pair, tmp_path):
    source = sample_pair[0]
    wb = load_workbook(source); ws = wb["Sheet0"]
    wb.properties.creator = "Gerçek Kişi"; wb.properties.lastModifiedBy = "Gerçek Personel"
    ws["A14"] = "Bağlantı"; ws["A14"].hyperlink = "https://example.com/private/12345678901"
    ws["B14"].comment = Comment("TC 12345678901", "Gerçek Kişi")
    wb.save(source)
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    target_wb = load_workbook(output); target = target_wb["Sheet0"]
    assert target_wb.properties.creator != "Gerçek Kişi" and target_wb.properties.lastModifiedBy != "Gerçek Personel"
    assert target["A14"].hyperlink is None and target["B14"].comment is None


def test_type_columns_are_preserved(sample_pair, tmp_path):
    outputs, _ = run_pair(sample_pair, tmp_path)
    source, target = load_workbook(sample_pair[0])["Sheet0"], load_workbook(outputs[0])["Sheet0"]
    for coord in ("C8", "C9", "C13"):
        assert target[coord].value == source[coord].value


def test_event_date_and_duration_are_preserved(sample_pair, tmp_path):
    outputs, _ = run_pair(sample_pair, tmp_path)
    source, target = load_workbook(sample_pair[0])["Sheet0"], load_workbook(outputs[0])["Sheet0"]
    for coord in ("E8", "F8", "E9", "F9", "D13", "E13"):
        assert target[coord].value == source[coord].value


def test_upload_download_sizes_are_preserved(sample_pair, tmp_path):
    outputs, _ = run_pair(sample_pair, tmp_path)
    source, target = load_workbook(sample_pair[0])["Sheet0"], load_workbook(outputs[0])["Sheet0"]
    for coord in ("H13", "I13"):
        assert target[coord].value == source[coord].value


def test_operator_is_preserved(sample_pair, tmp_path):
    source = sample_pair[0]
    wb = load_workbook(source); ws = wb["Sheet0"]
    ws["K12"] = "OPERATÖR"; ws["K13"] = "Turkcell"; wb.save(source)
    output = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD)).run([source], tmp_path / "out")[0]
    assert load_workbook(output)["Sheet0"]["K13"].value == "Turkcell"


def test_same_key_reproducible(sample_pair, tmp_path):
    out1, out2 = tmp_path / "o1", tmp_path / "o2"
    project = Project.create(tmp_path / "project", TEST_PASSWORD)
    a = AnonymizationSession(project).run(list(sample_pair), out1)
    project.save(); project.close()
    b = AnonymizationSession(Project.open(project.path, TEST_PASSWORD)).run(list(sample_pair), out2)
    for p, q in zip(a, b):
        wp, wq = load_workbook(p, data_only=False), load_workbook(q, data_only=False)
        assert [[c.value for row in sp.iter_rows() for c in row] for sp in wp] == [[c.value for row in sq.iter_rows() for c in row] for sq in wq]


def test_corrupted_mapping_collision_is_rejected(tmp_path):
    project = Project.create(tmp_path / "project", TEST_PASSWORD)
    try:
        MappingStore(project.secret, persistent_state={"phone": {"a": "555", "b": "555"}})
        assert False, "duplicate mapping accepted"
    except ValueError:
        pass


def test_excel_escape_and_control_character_cleanup():
    dirty = "  Birinci_x000D__x000A_İkinci&#13;&#10;Üçüncü\r\n\x01  "
    clean = sanitize_text(dirty)
    assert clean == "Birinci\n\nİkinci\n\nÜçüncü"
    assert "_x000" not in clean and "\r" not in clean and "\x01" not in clean


def test_single_pass_does_not_duplicate_identifiers(tmp_path):
    project = Project.create(tmp_path / "project", TEST_PASSWORD)
    engine = TextAnonymizer(AnonymizationSession(project).store)
    source = "Ara: 0532 123 45 67; tekrar 0532 123 45 67; IP 8.8.8.8"
    target, counts = engine.transform(source)
    assert counts == {"phone": 2, "ipv4": 1}
    assert engine.counts(target) == counts
    assert target.count(engine.store.phone("0532 123 45 67")) == 2


def test_project_file_contains_no_plaintext_source(sample_pair, tmp_path):
    outputs, session = run_pair(sample_pair, tmp_path)
    project_text = (session.project.path / "hts-projesi.json").read_text(encoding="utf-8")
    for forbidden in ("YILMAZ", "DEMİR", "0532 123 45 67", "12345678901"):
        assert forbidden not in project_text


def test_concatenated_phone_cell_is_simplified_before_mapping(tmp_path):
    project = Project.create(tmp_path / "project", TEST_PASSWORD)
    session = AnonymizationSession(project)
    raw = "55320111415327567111"
    normalized, simplified = normalize_phone_cell(raw)
    assert simplified and normalized == raw[:10]
    mapped = session._transform(raw, "phone", None)
    assert len(digits(mapped)) == 10
    assert digits(mapped)[:1] == raw[:1]
    assert digits(mapped)[1:10] != raw[1:10]
    assert raw[10:] not in mapped
    assert session.report.simplified_phone_cells == 1


def test_scientific_phone_value_is_expanded_without_extra_digits():
    normalized, simplified = normalize_phone_cell("5.532011141E+9")
    assert normalized == "5532011141"
    assert not simplified


def test_other_identifier_columns_are_simplified_by_type():
    cases = (
        ("1234567890198765432109", "tc", "12345678901"),
        ("490154203237518356938035643809", "imei", "490154203237518"),
        ("286011234567890286019876543210", "imsi", "286011234567890"),
        ("8.8.8.8 1.1.1.1", "ip", "8.8.8.8"),
        ("AA:BB:CC:DD:EE:FF AA:BB:CC:DD:EE:FF", "mac", "AA:BB:CC:DD:EE:FF"),
        ("ABC-123|ABC-123", "file_number", "ABC-123"),
    )
    for raw, category, expected in cases:
        normalized, simplified = normalize_classified_value(raw, category)
        assert simplified and normalized == expected


def test_general_simplification_happens_before_anonymization(tmp_path):
    session = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD))
    tc = session._transform("1234567890198765432109", "tc", None)
    imei = session._transform("490154203237518356938035643809", "imei", None)
    ip = session._transform("8.8.8.8 1.1.1.1", "ip", None)
    assert len(digits(tc)) == 11
    assert len(digits(imei)) == 15
    assert " " not in ip
    assert session.report.simplified_cells == {"tc": 1, "imei": 1, "ip": 1}


def test_prepare_honors_cancellation_and_closes_workbook(sample_pair, tmp_path):
    cancelled = threading.Event(); cancelled.set()
    session = AnonymizationSession(Project.create(tmp_path / "project", TEST_PASSWORD), cancel_event=cancelled)
    try:
        session.prepare([sample_pair[0]])
        assert False, "prepare cancellation was ignored"
    except InterruptedError:
        pass
