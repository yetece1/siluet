"""Parola pencereleri."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from ..crypto_store import MIN_PASSWORD_LENGTH
from .i18n import t


def _password_field() -> QLineEdit:
    field = QLineEdit()
    field.setEchoMode(QLineEdit.Password)
    field.setMinimumWidth(320)
    return field


def _labelled(layout: QVBoxLayout, text: str, field: QLineEdit) -> None:
    label = QLabel(text.upper())
    label.setObjectName("eyebrow")
    layout.addWidget(label)
    layout.addWidget(field)


def password_problem(first: str, second: str) -> str:
    """Yeni parola için kullanıcıya gösterilecek sorun; sorun yoksa boş metin."""
    if len(first) < MIN_PASSWORD_LENGTH:
        return t("pw.too_short", min=MIN_PASSWORD_LENGTH)
    if first != second:
        return t("pw.mismatch")
    return ""


class NewPasswordDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, intro: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName("h1")
        layout.addWidget(heading)
        if intro:
            text = QLabel(intro)
            text.setWordWrap(True)
            text.setObjectName("muted")
            layout.addWidget(text)
        layout.addSpacing(8)
        self.first, self.second = _password_field(), _password_field()
        _labelled(layout, t("pw.password"), self.first)
        _labelled(layout, t("pw.repeat"), self.second)
        self.warning = QLabel()
        self.warning.setObjectName("warning")
        layout.addWidget(self.warning)
        self.notice = QLabel(t("pw.notice"))
        self.notice.setWordWrap(True)
        self.notice.setObjectName("muted")
        layout.addWidget(self.notice)
        layout.addSpacing(6)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = self.buttons.button(QDialogButtonBox.Ok)
        ok.setText(t("pw.ok"))
        ok.setObjectName("primary")
        self.buttons.button(QDialogButtonBox.Cancel).setText(t("pw.cancel"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.first.textChanged.connect(self._revalidate)
        self.second.textChanged.connect(self._revalidate)
        self._revalidate()

    def _revalidate(self) -> None:
        problem = password_problem(self.first.text(), self.second.text())
        self.warning.setText(problem if (self.first.text() or self.second.text()) else "")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not problem)

    def password(self) -> str:
        return self.first.text()


class PasswordPromptDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, project_name: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName("h1")
        layout.addWidget(heading)
        self.field = _password_field()
        _labelled(layout, t("pw.prompt", name=project_name), self.field)
        self.error = QLabel()
        self.error.setObjectName("warning")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        layout.addSpacing(6)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = self.buttons.button(QDialogButtonBox.Ok)
        ok.setText(t("pw.open"))
        ok.setObjectName("primary")
        self.buttons.button(QDialogButtonBox.Cancel).setText(t("pw.cancel"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def password(self) -> str:
        return self.field.text()

    def show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()
        self.field.clear()
        self.field.setFocus()
