from pathlib import Path

from siluet.project import Project, ROLE_COUNTER, ROLE_MAIN
from siluet.ui.preflight import collect_xlsx, preflight
from siluet.ui.recent import RecentProjects

from conftest import TEST_PASSWORD


def test_collect_xlsx_folder_and_files(tmp_path: Path):
    (tmp_path / "b.XLSX").write_bytes(b"x")
    (tmp_path / "a.xlsx").write_bytes(b"x")
    (tmp_path / "~$kilit.xlsx").write_bytes(b"x")
    (tmp_path / "eski.xls").write_bytes(b"x")
    (tmp_path / "not.csv").write_bytes(b"x")
    nested = tmp_path / "alt"
    nested.mkdir()
    (nested / "nested.xlsx").write_bytes(b"x")
    loose = tmp_path / "tek.xlsx"
    loose.write_bytes(b"x")
    files, skipped = collect_xlsx([tmp_path, tmp_path / "a.xlsx", nested / "nested.xlsx", tmp_path / "eski.xls"])
    assert [p.name for p in files] == ["a.xlsx", "b.XLSX", "tek.xlsx", "nested.xlsx"]
    assert skipped == 3  # ~$kilit.xlsx, eski.xls (bir kez), not.csv


def _project_with_pair(tmp_path, sample_pair):
    project = Project.create(tmp_path / "proje", TEST_PASSWORD)
    group = project.add_group("G")
    project.add_file(group.group_id, sample_pair[0], ROLE_MAIN)
    project.add_file(group.group_id, sample_pair[1], ROLE_COUNTER)
    return project


def _codes(blockers):
    return [b.code for b in blockers]


def test_preflight_clean_returns_empty(tmp_path, sample_pair):
    project = _project_with_pair(tmp_path, sample_pair)
    assert preflight(project, tmp_path / "cikti", 0) == []


def test_preflight_no_files(tmp_path):
    project = Project.create(tmp_path / "proje", TEST_PASSWORD)
    assert _codes(preflight(project, tmp_path / "cikti", 0)) == ["no_files"]


def test_preflight_no_output(tmp_path, sample_pair):
    assert _codes(preflight(_project_with_pair(tmp_path, sample_pair), None, 0)) == ["no_output"]


def test_preflight_output_exists(tmp_path, sample_pair):
    out = tmp_path / "cikti"
    out.mkdir()
    (out / "ana.xlsx").write_bytes(b"x")
    blockers = preflight(_project_with_pair(tmp_path, sample_pair), out, 0)
    assert _codes(blockers) == ["output_exists"] and "ana.xlsx" in blockers[0].message


def test_preflight_output_inside_source(tmp_path, sample_pair):
    blockers = preflight(_project_with_pair(tmp_path, sample_pair), sample_pair[0].parent, 0)
    assert "output_inside_source" in _codes(blockers)


def test_preflight_source_missing(tmp_path, sample_pair):
    project = _project_with_pair(tmp_path, sample_pair)
    sample_pair[1].unlink()
    blockers = preflight(project, tmp_path / "cikti", 0)
    assert _codes(blockers) == ["source_missing"] and "karsi.xlsx" in blockers[0].message


def test_preflight_duplicate_names(tmp_path, sample_pair):
    project = _project_with_pair(tmp_path, sample_pair)
    other = tmp_path / "baska"
    other.mkdir()
    twin = other / "ana.xlsx"
    twin.write_bytes(sample_pair[0].read_bytes())
    project.add_file(project.groups[0].group_id, twin, ROLE_MAIN)
    assert "duplicate_names" in _codes(preflight(project, tmp_path / "cikti", 0))


def test_preflight_ambiguous_pending(tmp_path, sample_pair):
    assert _codes(preflight(_project_with_pair(tmp_path, sample_pair), tmp_path / "cikti", 2)) == ["ambiguous_pending"]


def test_preflight_output_not_writable(tmp_path, sample_pair, monkeypatch):
    from siluet.ui import preflight as module
    monkeypatch.setattr(module, "_writable", lambda _path: False)
    assert _codes(preflight(_project_with_pair(tmp_path, sample_pair), tmp_path / "cikti", 0)) == ["output_not_writable"]


class FakeSettings(dict):
    def value(self, key, default=None):
        return self.get(key, default)

    def setValue(self, key, value):
        self[key] = value


def test_recent_projects_cap_order_and_missing(tmp_path):
    recent = RecentProjects(FakeSettings())
    folders = []
    for index in range(10):
        folder = tmp_path / f"p{index}"
        folder.mkdir()
        folders.append(folder)
        recent.add(folder)
    recent.add(folders[3])
    listed = recent.list()
    assert len(listed) == 8 and listed[0] == folders[3].resolve() and listed[1] == folders[9].resolve()
    folders[9].rmdir()
    assert folders[9].resolve() not in recent.list()


def test_preflight_only_ambiguous_files_asks_for_role(tmp_path):
    project = Project.create(tmp_path / "proje", TEST_PASSWORD)
    assert _codes(preflight(project, tmp_path / "cikti", 1)) == ["ambiguous_pending"]


def test_collect_xlsx_counts_subfolders(tmp_path: Path):
    from siluet.ui.preflight import collect_xlsx_report
    (tmp_path / "a.xlsx").write_bytes(b"x")
    for name in ("dosya-1", "dosya-2"):
        sub = tmp_path / name
        sub.mkdir()
        (sub / "ic.xlsx").write_bytes(b"x")
    report = collect_xlsx_report([tmp_path])
    assert [p.name for p in report.files] == ["a.xlsx"]
    assert report.skipped_files == 0 and report.skipped_folders == 2


def test_collect_xlsx_unreadable_folder(tmp_path: Path, monkeypatch):
    from siluet.ui.preflight import collect_xlsx_report
    folder = tmp_path / "kilitli"
    folder.mkdir()
    def denied(self):
        raise PermissionError("erişim yok")
    monkeypatch.setattr(Path, "iterdir", denied)
    report = collect_xlsx_report([folder])
    assert report.files == [] and report.unreadable == [folder]
