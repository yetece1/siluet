from pathlib import Path

from openpyxl import Workbook

from conftest import TEST_PASSWORD
from siluet.auto_classifier import classify_files
from siluet.group_processor import GroupProcessor
from siluet.project import Project, ROLE_COUNTER, ROLE_MAIN


def _book(path: Path, primary: str, main: bool, case: str = "2026/100"):
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet0"
    ws.append([f"DOSYA NO: {case}"])
    ws.append(["GSM GÖRÜŞME SORGU SONUÇLARI"])
    ws.append(["SIRA NO", "NUMARA", "DİĞER NUMARA", "BAZ (Numara)"])
    ws.append([1, primary, "05321112233", "ANKARA-CANKAYA-001"])
    if main:
        ws.append(["İNTERNET BAĞLANTI (GPRS) İLETİŞİM SORGU SONUÇLARI"])
        ws.append(["SIRA NO", "NUMARA", "KAYNAK IP", "BAZ (Numara)"])
        ws.append([1, primary, "8.8.8.8", "ANKARA-CANKAYA-001"])
    wb.save(path)


def test_content_based_roles_ignore_filenames(tmp_path):
    main = tmp_path / "rastgele-z.xlsx"
    counter = tmp_path / "rastgele-q.xlsx"
    _book(main, "05320000001", True)
    _book(counter, "05320000001", False)
    groups, ambiguous, failures = classify_files([counter, main])
    assert not ambiguous and not failures
    assert len(groups) == 1
    assert {p.role for p in groups[0].profiles} == {ROLE_MAIN, ROLE_COUNTER}


def test_many_files_pair_without_cross_mixing(tmp_path):
    paths = []
    for index in range(60):
        primary = f"0532{index:07d}"
        case = f"2026/{1000 + index}"
        main = tmp_path / f"alpha-{index}.xlsx"
        counter = tmp_path / f"omega-{index}.xlsx"
        _book(main, primary, True, case)
        _book(counter, primary, False, case)
        paths.extend([counter, main])
    groups, ambiguous, failures = classify_files(paths)
    assert not ambiguous and not failures
    assert len(groups) == 60
    assert all(len(g.profiles) == 2 for g in groups)
    assert len({p.path for g in groups for p in g.profiles}) == 120


def test_broken_file_does_not_stop_batch(tmp_path):
    main, counter = tmp_path / "m.xlsx", tmp_path / "c.xlsx"
    _book(main, "05320000001", True)
    _book(counter, "05320000001", False)
    broken = tmp_path / "broken.xlsx"
    broken.write_text("not an xlsx", encoding="utf-8")
    groups, ambiguous, failures = classify_files([main, broken, counter])
    assert len(groups) == 1 and not ambiguous
    assert len(failures) == 1 and failures[0].path == broken


def test_classification_cancellation_is_not_reported_as_file_failure(tmp_path):
    source = tmp_path / "cancel.xlsx"
    _book(source, "05320000001", True)
    try:
        classify_files([source], cancelled=lambda: True)
        assert False, "cancellation was ignored"
    except InterruptedError:
        pass


def test_same_directory_alone_is_not_pair_evidence(tmp_path):
    main, counter = tmp_path / "unrelated-main-x.xlsx", tmp_path / "unrelated-counter-y.xlsx"
    _book(main, "05320000001", True, "2026/111")
    _book(counter, "05329999999", False, "2026/999")
    groups, ambiguous, failures = classify_files([main, counter])
    assert not ambiguous and not failures
    assert len(groups) == 2
    assert all(len(group.profiles) == 1 for group in groups)


def test_automatic_group_names_never_collide_when_numbers_have_gaps(tmp_path):
    main, counter = tmp_path / "m.xlsx", tmp_path / "c.xlsx"
    _book(main, "05320000001", True)
    _book(counter, "05320000001", False)
    groups, _, _ = classify_files([main, counter])
    project = Project.create(tmp_path / "project", TEST_PASSWORD)
    project.add_group("Otomatik 002")
    assert project.add_auto_groups(groups) == 2
    names = [group.name for group in project.groups]
    assert len(names) == len(set(name.casefold() for name in names))


def test_bulk_add_rolls_back_memory_when_project_save_fails(tmp_path, monkeypatch):
    main, counter = tmp_path / "m.xlsx", tmp_path / "c.xlsx"
    _book(main, "05320000001", True)
    _book(counter, "05320000001", False)
    groups, _, _ = classify_files([main, counter])
    project = Project.create(tmp_path / "project", TEST_PASSWORD)
    before = list(project.groups)
    monkeypatch.setattr(project, "save", lambda: (_ for _ in ()).throw(OSError("disk full")))
    try:
        project.add_auto_groups(groups)
        assert False, "save failure was ignored"
    except OSError:
        pass
    assert project.groups == before


def test_auto_pair_is_consistent_main_number_changes_and_base_stays(tmp_path):
    main, counter = tmp_path / "x.xlsx", tmp_path / "y.xlsx"
    _book(main, "05320000001", True)
    _book(counter, "05320000001", False)
    groups, ambiguous, failures = classify_files([main, counter])
    project = Project.create(tmp_path / "project", TEST_PASSWORD)
    assert project.add_auto_groups(groups) == 2
    result = GroupProcessor(project, tmp_path / "out").process()[0]
    outputs = {item.source: item.output for item in result.files}
    from openpyxl import load_workbook
    source_main = load_workbook(main).active
    out_main = load_workbook(outputs[main.resolve()]).active
    out_counter = load_workbook(outputs[counter.resolve()]).active
    assert out_main["B4"].value != source_main["B4"].value
    assert out_main["B4"].value == out_counter["B4"].value
    assert out_main["D4"].value == source_main["D4"].value
