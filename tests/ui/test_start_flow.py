import base64
import json
import secrets

import pytest

from siluet.migration import BACKUP_NAME
from siluet.project import PROJECT_FILE, Project
from siluet.ui.app import MainWindow

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
    win.inform = lambda *args, **kwargs: win.messages.append(args)
    win.messages = []
    yield win
    win.close_project()


def test_create_then_reopen(window, tmp_path):
    folder = tmp_path / "yeni"
    window.ask_directory = lambda _title: folder
    window.ask_new_password = lambda _title, _intro="": TEST_PASSWORD
    window.create_project()
    assert window.project is not None and window.stack.currentIndex() == 1
    assert "yeni" in window.windowTitle()
    window.close_project()
    assert window.stack.currentIndex() == 0 and window.project is None
    window.ask_password = lambda _name, _error: TEST_PASSWORD
    window.open_project()
    assert window.project is not None and window.project.path == folder.resolve()


def test_create_in_existing_project_folder_refused(window, tmp_path):
    Project.create(tmp_path / "var", TEST_PASSWORD).close()
    window.ask_directory = lambda _title: tmp_path / "var"
    window.ask_new_password = lambda *_a: pytest.fail("parola sorulmamalı")
    window.create_project()
    assert window.project is None and window.messages


def test_open_folder_without_project(window, tmp_path):
    window.ask_directory = lambda _title: tmp_path
    window.open_project()
    assert window.project is None and "projesi yok" in window.messages[-1][1]


def test_wrong_password_shows_error_and_stays_on_start(window, tmp_path):
    Project.create(tmp_path / "p", TEST_PASSWORD).close()
    attempts = iter(["yanlis-parola-1", None])
    errors = []
    def ask(_name, error):
        errors.append(error)
        return next(attempts)
    window.ask_directory = lambda _title: tmp_path / "p"
    window.ask_password = ask
    window.open_project()
    assert window.project is None and window.stack.currentIndex() == 0
    assert errors[0] is None and "Parola yanlış" in errors[1]


def test_open_legacy_migrates(window, tmp_path):
    folder = tmp_path / "eski"
    folder.mkdir()
    payload = {"version": 2, "project_id": "x", "internal_key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
               "groups": [], "mapping_scope": "group"}
    (folder / PROJECT_FILE).write_text(json.dumps(payload))
    window.ask_directory = lambda _title: folder
    window.ask_new_password = lambda _title, _intro="": TEST_PASSWORD
    confirmations = []
    window.confirm = lambda title, text: confirmations.append(text) or True
    window.open_project()
    assert window.project is not None and Project.detect_version(folder) == 3
    assert any("telefon" in text.lower() for text in confirmations)
    assert not (folder / BACKUP_NAME).exists()


def test_locked_project_message(window, tmp_path):
    held = Project.create(tmp_path / "p", TEST_PASSWORD)
    window.ask_password = lambda _name, _error: TEST_PASSWORD
    window.open_path(tmp_path / "p")
    assert window.project is None and "açık" in window.messages[-1][1]
    held.close()


def test_recent_list_updated(window, tmp_path):
    window.ask_directory = lambda _title: tmp_path / "a"
    window.ask_new_password = lambda _title, _intro="": TEST_PASSWORD
    window.create_project()
    window.close_project()
    assert window.recent.list() == [(tmp_path / "a").resolve()]
    assert window.start_view.recent_list.count() == 1


def test_minimum_size(window):
    assert window.minimumWidth() >= 960 and window.minimumHeight() >= 640


def test_leftover_backup_offered_for_deletion_on_open(window, tmp_path):
    from siluet.migration import BACKUP_NAME
    Project.create(tmp_path / "p", TEST_PASSWORD).close()
    backup = tmp_path / "p" / BACKUP_NAME
    backup.write_text('{"internal_key": "duz-metin"}')
    asked = []
    window.confirm = lambda title, text: asked.append(text) or True
    window.ask_password = lambda _name, _error: TEST_PASSWORD
    window.open_path(tmp_path / "p")
    assert window.project is not None
    assert asked and BACKUP_NAME in asked[0]
    assert not backup.exists()


def test_malformed_project_header_shows_message(window, tmp_path):
    folder = tmp_path / "bozuk"
    folder.mkdir()
    (folder / PROJECT_FILE).write_text(json.dumps({"format": "hts-anonimlestirici", "version": None}))
    window.open_path(folder)
    assert window.project is None and window.messages
