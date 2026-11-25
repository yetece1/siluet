from PySide6.QtWidgets import QDialogButtonBox

from siluet.ui.dialogs import NewPasswordDialog, PasswordPromptDialog


def test_new_password_dialog_validation(qtbot):
    dialog = NewPasswordDialog(None, "Yeni proje")
    qtbot.addWidget(dialog)
    ok = dialog.buttons.button(QDialogButtonBox.Ok)
    assert not ok.isEnabled()
    dialog.first.setText("kisa")
    dialog.second.setText("kisa")
    assert not ok.isEnabled() and "10" in dialog.warning.text()
    dialog.first.setText("uzun-parola-1")
    dialog.second.setText("uzun-parola-2")
    assert not ok.isEnabled() and "eşleşmiyor" in dialog.warning.text()
    dialog.second.setText("uzun-parola-1")
    assert ok.isEnabled()
    assert dialog.password() == "uzun-parola-1"
    assert "unutulursa" in dialog.notice.text()


def test_password_prompt_shows_error(qtbot):
    dialog = PasswordPromptDialog(None, "Proje aç", "proje")
    qtbot.addWidget(dialog)
    dialog.field.setText("abc")
    assert dialog.password() == "abc"
    dialog.show_error("Parola yanlış")
    assert dialog.error.text() == "Parola yanlış" and not dialog.error.isHidden()
    assert dialog.field.text() == ""
