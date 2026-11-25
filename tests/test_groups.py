from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from openpyxl import load_workbook

from conftest import TEST_PASSWORD
from siluet.group_processor import GroupProcessor
from siluet.project import Project, ROLE_COUNTER, ROLE_MAIN, SCOPE_GROUP, SCOPE_PROJECT


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def add_pair(project, group_name, pair):
    group = project.add_group(group_name)
    for path, role in zip(pair, (ROLE_MAIN, ROLE_COUNTER)):
        project.add_file(group.group_id, path, role, ["Sheet0"])
    return group


def phone(path, coord="B3"):
    return load_workbook(path, data_only=False)["Sheet0"][coord].value


def test_unlimited_groups_and_duplicate_rejected(sample_pair, tmp_path):
    project = Project.create(tmp_path / "project", TEST_PASSWORD)
    for number in range(60): project.add_group(f"Grup {number}")
    project.add_file(project.groups[0].group_id, sample_pair[0], ROLE_MAIN, ["Sheet0"])
    try:
        project.add_file(project.groups[1].group_id, sample_pair[0], ROLE_COUNTER, ["Sheet0"])
        assert False, "duplicate accepted"
    except ValueError: pass
    assert len(project.groups) == 60


def test_group_isolation_relations_structure_base_and_originals(sample_pair, tmp_path):
    before = {p: sha(p) for p in sample_pair}; project = Project.create(tmp_path / "project", TEST_PASSWORD)
    add_pair(project, "İnceleme 01", sample_pair)
    results = GroupProcessor(project, tmp_path / "out").process()
    assert results[0].successful
    outputs = [x.output for x in results[0].files]
    assert phone(outputs[0], "B3") == phone(outputs[1], "B4")
    for source, output in zip(sample_pair, outputs):
        a, b = load_workbook(source), load_workbook(output)
        assert a.sheetnames == b.sheetnames == ["Sheet0"]
        assert a["Sheet0"].max_row == b["Sheet0"].max_row
        assert a["Sheet0"]["J8"].value == b["Sheet0"]["J8"].value
        assert sha(source) == before[source]
    assert {path.name for path in (tmp_path / "out").iterdir()} == {"ana.xlsx", "karsi.xlsx"}


def test_unique_marker_and_sheets_never_cross_files(sample_pair, tmp_path):
    a, b = sample_pair
    wb = load_workbook(a); wb["Sheet0"]["K14"] = "YALNIZ_A_12345678901"; wb.create_sheet("Yalniz_A"); wb.save(a)
    wb = load_workbook(b); wb["Sheet0"]["K15"] = "YALNIZ_B_98765432109"; wb.save(b)
    project = Project.create(tmp_path / "project", TEST_PASSWORD); add_pair(project, "G", sample_pair)
    result = GroupProcessor(project, tmp_path / "out").process()[0]
    out_a, out_b = [x.output for x in result.files]
    assert "Yalniz_A" in load_workbook(out_a).sheetnames and "Yalniz_A" not in load_workbook(out_b).sheetnames
    sheet_a, sheet_b = load_workbook(out_a)["Sheet0"], load_workbook(out_b)["Sheet0"]
    values_a = str([[c.value for c in row] for row in sheet_a.iter_rows()])
    values_b = str([[c.value for c in row] for row in sheet_b.iter_rows()])
    marker_a, marker_b = sheet_a["K14"].value, sheet_b["K15"].value
    assert marker_a != "YALNIZ_A_12345678901" and marker_b != "YALNIZ_B_98765432109"
    assert str(marker_a) not in values_b and str(marker_b) not in values_a
    assert "YALNIZ_A_12345678901" not in values_a + values_b
    assert "YALNIZ_B_98765432109" not in values_a + values_b


def test_same_filename_is_rejected_in_flat_output(sample_pair, tmp_path):
    p1, p2 = tmp_path / "a" / "kayit.xlsx", tmp_path / "b" / "kayit.xlsx"
    p1.parent.mkdir(); p2.parent.mkdir(); shutil.copy2(sample_pair[0], p1); shutil.copy2(sample_pair[1], p2)
    project=Project.create(tmp_path/"project", TEST_PASSWORD); group=project.add_group("G")
    project.add_file(group.group_id,p1,ROLE_MAIN); project.add_file(group.group_id,p2,ROLE_MAIN)
    try:
        GroupProcessor(project,tmp_path/"out").process()
        assert False, "same-name sources were accepted"
    except ValueError as exc:
        assert "Aynı adlı" in str(exc)


def test_failure_can_continue_without_damaging_other_file(sample_pair, tmp_path):
    project=Project.create(tmp_path/"project", TEST_PASSWORD); group=project.add_group("G")
    project.add_file(group.group_id,tmp_path/"missing.xlsx",ROLE_MAIN); project.add_file(group.group_id,sample_pair[1],ROLE_COUNTER)
    result=GroupProcessor(project,tmp_path/"out",continue_on_error=True).process()[0]
    assert result.files[0].status == "başarısız" and result.files[1].status == "başarılı" and result.files[1].output.exists()


def test_progress_reaches_total_with_failed_and_valid_files(sample_pair, tmp_path):
    project=Project.create(tmp_path/"project", TEST_PASSWORD); group=project.add_group("G")
    project.add_file(group.group_id,tmp_path/"missing.xlsx",ROLE_MAIN)
    project.add_file(group.group_id,sample_pair[0],ROLE_COUNTER)
    updates=[]
    GroupProcessor(project,tmp_path/"out",progress=lambda done,total,*_: updates.append((done,total)),continue_on_error=True).process()
    assert updates and updates[-1] == (2,2)
    assert [done for done,_ in updates] == sorted(done for done,_ in updates)


def test_project_scope_consistent_and_group_scope_independent(sample_pair, tmp_path):
    def run(scope, root):
        project=Project.create(root/"project", TEST_PASSWORD); project.mapping_scope=scope
        copies=[]
        for number in (1,2):
            path=root/f"g{number}.xlsx"; shutil.copy2(sample_pair[0],path); copies.append(path)
            group=project.add_group(f"G{number}"); project.add_file(group.group_id,path,ROLE_MAIN)
        project.save(); results=GroupProcessor(project,root/"out").process()
        return [phone(r.files[0].output) for r in results]
    global_values=run(SCOPE_PROJECT,tmp_path/"global"); group_values=run(SCOPE_GROUP,tmp_path/"local")
    assert global_values[0] == global_values[1]
    assert group_values[0] != group_values[1]


def test_output_contains_only_source_named_excel_files(sample_pair, tmp_path):
    project=Project.create(tmp_path/"project", TEST_PASSWORD)
    for index,path in enumerate(sample_pair):
        group=project.add_group(f"R{index}");project.add_file(group.group_id,path,ROLE_MAIN)
    GroupProcessor(project,tmp_path/"out").process()
    files = sorted(path.name for path in (tmp_path / "out").iterdir())
    assert files == ["ana.xlsx", "karsi.xlsx"]
    assert all(path.suffix == ".xlsx" and path.is_file() for path in (tmp_path / "out").iterdir())


def test_existing_output_is_not_overwritten(sample_pair, tmp_path):
    project = Project.create(tmp_path / "project", TEST_PASSWORD)
    group = project.add_group("G")
    project.add_file(group.group_id, sample_pair[0], ROLE_MAIN)
    output = tmp_path / "out"
    output.mkdir()
    existing = output / sample_pair[0].name
    existing.write_bytes(b"keep")
    try:
        GroupProcessor(project, output).process()
        assert False, "existing output was accepted"
    except FileExistsError:
        pass
    assert existing.read_bytes() == b"keep"
