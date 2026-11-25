from pathlib import Path

import pytest
from PySide6.QtWidgets import QComboBox

from siluet import group_processor
from siluet.auto_classifier import WorkbookProfile
from siluet.project import Project, ROLE_COUNTER, ROLE_MAIN
from siluet.ui.project_view import ProjectView

from conftest import TEST_PASSWORD


class FakeSettings(dict):
    def value(self, key, default=None):
        return self.get(key, default)

    def setValue(self, key, value):
        self[key] = value


@pytest.fixture
def view(qtbot, tmp_path):
    project = Project.create(tmp_path / "proje", TEST_PASSWORD)
    widget = ProjectView(project, FakeSettings())
    widget.results_shown = []
    widget.show_result = lambda results, output: widget.results_shown.append((results, output))
    widget.inform = lambda *args, **kwargs: None
    qtbot.addWidget(widget)
    yield widget
    project.close()


def _files(view):
    return {Path(e.path).name: e.role for g in view.project.groups for e in g.files}


def _add(view, qtbot, paths):
    view.add_paths(paths)
    qtbot.waitUntil(lambda: not view.is_busy(), timeout=20000)


def test_default_output_dir(view):
    assert view.output_dir == view.project.path / "Siluet_Cikti"


def test_add_pair_adds_both_files(view, qtbot, sample_pair):
    _add(view, qtbot, [sample_pair[0].parent])
    assert set(_files(view)) == {"ana.xlsx", "karsi.xlsx"}
    assert view.tree.file_item(sample_pair[0]) is not None
    assert view.blockers() == []


def test_adding_same_files_again_is_noop(view, qtbot, sample_pair):
    _add(view, qtbot, list(sample_pair))
    _add(view, qtbot, list(sample_pair))
    assert sum(len(g.files) for g in view.project.groups) == 2
    assert "zaten" in view.banner.text()


def test_role_change_persists(view, qtbot, sample_pair, tmp_path):
    _add(view, qtbot, list(sample_pair))
    item = view.tree.file_item(sample_pair[1])
    combo = view.tree.itemWidget(item, 1)
    assert isinstance(combo, QComboBox)
    target = ROLE_COUNTER if _files(view)["karsi.xlsx"] == ROLE_MAIN else ROLE_MAIN
    combo.setCurrentIndex(combo.findData(target))
    view.project.close()
    reopened = Project.open(tmp_path / "proje", TEST_PASSWORD)
    assert {Path(e.path).name: e.role for g in reopened.groups for e in g.files}["karsi.xlsx"] == target
    view.project = reopened


def test_ambiguous_requires_choice(view, qtbot, sample_pair):
    profile = WorkbookProfile(Path(sample_pair[0]).resolve(), ["Sheet0"])
    view.apply_classification(([], [profile], []))
    assert [b.code for b in view.blockers()] == ["ambiguous_pending"]
    item = view.tree.ambiguous_item(sample_pair[0])
    combo = view.tree.itemWidget(item, 1)
    combo.setCurrentIndex(combo.findData(ROLE_MAIN))
    assert view.blockers() == []
    assert _files(view) == {"ana.xlsx": ROLE_MAIN}
    assert not view.start_button.isHidden() and view.start_button.isEnabled()


def test_unreadable_files_reported_in_banner(view, qtbot, tmp_path):
    broken = tmp_path / "bozuk.xlsx"
    broken.write_bytes(b"bu bir excel degil")
    _add(view, qtbot, [broken])
    assert "bozuk.xlsx" in view.banner.text() and not view.banner.isHidden()
    assert _files(view) == {}


def test_move_file_to_new_group(view, qtbot, sample_pair):
    _add(view, qtbot, list(sample_pair))
    view.ask_text = lambda *_a: "Elle çift"
    view.move_to_new_group([sample_pair[1]])
    names = {g.name: [Path(e.path).name for e in g.files] for g in view.project.groups}
    assert names["Elle çift"] == ["karsi.xlsx"]


def test_remove_file(view, qtbot, sample_pair):
    _add(view, qtbot, list(sample_pair))
    view.remove_files([sample_pair[0]])
    assert set(_files(view)) == {"karsi.xlsx"}


def test_run_produces_outputs_and_result(view, qtbot, sample_pair):
    _add(view, qtbot, list(sample_pair))
    view.start()
    qtbot.waitUntil(lambda: bool(view.results_shown), timeout=30000)
    results, output = view.results_shown[0]
    assert output == view.output_dir
    assert sorted(p.name for p in output.iterdir()) == ["ana.xlsx", "karsi.xlsx"]
    assert all(r.successful for r in results)
    assert view.blockers()[0].code == "output_exists"


def test_source_removed_during_run(view, qtbot, sample_pair, monkeypatch):
    _add(view, qtbot, list(sample_pair))
    original = group_processor.AnonymizationSession.anonymize_file
    def remove_other(self, source, output, selected=None):
        result = original(self, source, output, selected)
        for path in sample_pair:
            if Path(path).resolve() != Path(source).resolve():
                Path(path).unlink(missing_ok=True)
        return result
    monkeypatch.setattr(group_processor.AnonymizationSession, "anonymize_file", remove_other)
    view.start()
    qtbot.waitUntil(lambda: bool(view.results_shown), timeout=30000)
    results, output = view.results_shown[0]
    statuses = [f.status for r in results for f in r.files]
    assert sorted(statuses) == ["başarılı", "başarısız"]
    assert len([p for p in output.iterdir() if p.suffix == ".xlsx"]) == 1
    assert view.add_button.isEnabled()


def test_existing_output_blocks_start(view, qtbot, sample_pair):
    _add(view, qtbot, list(sample_pair))
    view.output_dir.mkdir(parents=True)
    (view.output_dir / "ana.xlsx").write_bytes(b"x")
    view.refresh()
    assert not view.start_button.isEnabled()
    assert "ana.xlsx" in view.blocker_label.text()


def test_controls_locked_while_running(view, qtbot, sample_pair):
    _add(view, qtbot, list(sample_pair))
    view.start()
    assert view.is_busy() and not view.add_button.isEnabled() and view.cancel_button.isEnabled()
    qtbot.waitUntil(lambda: not view.is_busy(), timeout=30000)
    assert view.add_button.isEnabled() and not view.cancel_button.isEnabled()


def test_view_destroyed_while_running_does_not_abort(qtbot, tmp_path, sample_pair):
    from siluet.ui import workers
    project = Project.create(tmp_path / "proje2", TEST_PASSWORD)
    widget = ProjectView(project, FakeSettings())
    widget.inform = lambda *a, **k: None
    widget.add_paths(list(sample_pair))
    widget.deleteLater()
    qtbot.wait(50)
    qtbot.waitUntil(lambda: not workers._ACTIVE, timeout=20000)
    project.close()



def test_subfolders_reported_in_banner(view, qtbot, tmp_path, sample_pair):
    case = tmp_path / "dava"
    (case / "alt").mkdir(parents=True)
    (case / "alt" / "x.xlsx").write_bytes(Path(sample_pair[0]).read_bytes())
    view.add_paths([case])
    assert "alt klasör" in view.banner.text()
