"""Yeni arayüz: dil, tema, kenar çubuğu ve adımlar."""
import pytest

from siluet.ui import i18n
from siluet.ui.app import MainWindow
from siluet.ui.theme import TOKENS

from conftest import TEST_PASSWORD


class FakeSettings(dict):
    def value(self, key, default=None):
        return self.get(key, default)

    def setValue(self, key, value):
        self[key] = value


@pytest.fixture
def window(qtbot):
    win = MainWindow(settings=FakeSettings())
    qtbot.addWidget(win)
    win.messages = []
    win.inform = lambda *args, **kwargs: win.messages.append(args)
    yield win
    win.close_project()
    i18n.set_language("tr")


def _open_with_pair(window, tmp_path, qtbot, sample_pair):
    window.ask_directory = lambda _title: tmp_path / "proje"
    window.ask_new_password = lambda *_a: TEST_PASSWORD
    window.create_project()
    view = window.project_view
    view.inform = lambda *a, **k: None
    view.add_paths(list(sample_pair))
    qtbot.waitUntil(lambda: not view.is_busy(), timeout=20000)
    return view


def test_every_key_exists_in_both_languages():
    assert set(i18n.STRINGS["tr"]) == set(i18n.STRINGS["en"])
    for key, value in i18n.STRINGS["tr"].items():
        assert value.strip() and i18n.STRINGS["en"][key].strip(), key


def test_placeholders_match_between_languages():
    import string
    fields = lambda text: {f for _, f, _, _ in string.Formatter().parse(text) if f}
    for key in i18n.STRINGS["tr"]:
        assert fields(i18n.STRINGS["tr"][key]) == fields(i18n.STRINGS["en"][key]), key


def test_theme_tokens_complete():
    assert set(TOKENS["light"]) == set(TOKENS["dark"])


def test_language_switch_translates_and_persists(window):
    assert window.start_view.new_button.text() == i18n.STRINGS["tr"]["start.new"]
    window.lang_en.click()
    assert window.settings["language"] == "en"
    assert window.start_view.new_button.text() == i18n.STRINGS["en"]["start.new"]
    window.lang_tr.click()
    assert window.start_view.new_button.text() == i18n.STRINGS["tr"]["start.new"]


def test_language_switch_keeps_open_project_and_state(window, tmp_path, qtbot, sample_pair):
    view = _open_with_pair(window, tmp_path, qtbot, sample_pair)
    project = window.project
    view.go_to_step(1)
    window.lang_en.click()
    assert window.project is project
    assert window.project_view is not view
    assert window.project_view.step == 1
    assert window.project_view.next_button.text() == i18n.STRINGS["en"]["step.next"]


def test_theme_toggle_switches_palette_and_persists(window, qapp):
    before = qapp.palette().window().color().name()
    window.theme_button.click()
    after = qapp.palette().window().color().name()
    assert before != after
    assert window.settings["theme"] in {"light", "dark"}
    assert after.lower() == TOKENS[window.settings["theme"]]["bg"].lower()


def test_toggles_locked_while_busy(window, tmp_path, qtbot, sample_pair):
    view = _open_with_pair(window, tmp_path, qtbot, sample_pair)
    view.show_result = lambda *a: None
    view.start()
    assert not window.lang_en.isEnabled()
    qtbot.waitUntil(lambda: not view.is_busy(), timeout=30000)
    assert window.lang_en.isEnabled()


def test_sidebar_shows_project(window, tmp_path, qtbot, sample_pair):
    _open_with_pair(window, tmp_path, qtbot, sample_pair)
    assert window.sidebar_project_name.text() == "proje"
    assert not window.sidebar_project_box.isHidden()
    window.close_project()
    assert window.sidebar_project_box.isHidden()


def test_steps_flow(window, tmp_path, qtbot, sample_pair):
    window.ask_directory = lambda _title: tmp_path / "proje"
    window.ask_new_password = lambda *_a: TEST_PASSWORD
    window.create_project()
    view = window.project_view
    assert view.step == 0 and not view.next_button.isEnabled()
    view.add_paths(list(sample_pair))
    qtbot.waitUntil(lambda: not view.is_busy(), timeout=20000)
    assert view.next_button.isEnabled()
    view.next_button.click()
    assert view.step == 1 and view.start_button.isEnabled()
    assert "4" not in view.stat_labels["groups"].text() and view.stat_labels["files"].text() == "2"
    view.back_button.click()
    assert view.step == 0


def test_results_shown_inline(window, tmp_path, qtbot, sample_pair):
    view = _open_with_pair(window, tmp_path, qtbot, sample_pair)
    view.go_to_step(1)
    view.start()
    assert view.step == 2
    qtbot.waitUntil(lambda: not view.is_busy(), timeout=30000)
    qtbot.waitUntil(lambda: view.result_ok.text() == "2", timeout=5000)
    assert view.result_failed.text() == "0"
    view.new_run_button.click()
    assert view.step == 0
