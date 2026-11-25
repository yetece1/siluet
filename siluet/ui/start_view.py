"""Başlangıç ekranı: yeni proje, proje aç, son projeler."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from . import icons
from .i18n import t
from .theme import tokens


def eyebrow(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("eyebrow")
    return label


def rule() -> QFrame:
    line = QFrame()
    line.setObjectName("rule")
    return line


class ActionCard(QPushButton):
    """İki satırlı büyük eylem düğmesi: numara, başlık ve açıklama."""

    def __init__(self, icon_name: str, title: str, hint: str, primary: bool = False) -> None:
        super().__init__()
        tok = tokens()
        self.setObjectName("action_card")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(150)
        layout = QGridLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setVerticalSpacing(6)
        tile = QLabel()
        tile.setFixedSize(44, 44)
        tile.setAlignment(Qt.AlignCenter)
        tile.setPixmap(icons.pixmap(icon_name, tok["on_accent"] if primary else tok["ink"], 20))
        tile.setStyleSheet(f"background: {tok['accent'] if primary else tok['sunken']}; border-radius: 14px;")
        heading = QLabel(title)
        heading.setObjectName("h2")
        detail = QLabel(hint)
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        arrow = QLabel()
        arrow.setPixmap(icons.pixmap("arrow_right", tok["muted"], 18))
        for widget in (tile, heading, detail, arrow):
            widget.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(tile, 0, 0, Qt.AlignLeft)
        layout.addWidget(arrow, 0, 1, Qt.AlignRight | Qt.AlignTop)
        layout.setRowMinimumHeight(1, 10)
        layout.addWidget(heading, 2, 0, 1, 2)
        layout.addWidget(detail, 3, 0, 1, 2)
        self.title = heading.text()

    def text(self) -> str:  # testler ve erişilebilirlik için başlık
        return self.title


class StartView(QWidget):
    create_requested = Signal()
    open_requested = Signal()
    recent_selected = Signal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("content")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(56, 56, 56, 40)
        outer.setSpacing(0)
        outer.addWidget(eyebrow(t("start.eyebrow")))
        outer.addSpacing(10)
        headline = QLabel(t("app.tagline"))
        headline.setObjectName("display")
        headline.setWordWrap(True)
        outer.addWidget(headline)
        outer.addSpacing(10)
        description = QLabel(t("app.description"))
        description.setObjectName("muted")
        description.setWordWrap(True)
        description.setMaximumWidth(640)
        outer.addWidget(description)
        outer.addSpacing(32)

        actions = QHBoxLayout()
        actions.setSpacing(14)
        self.new_button = ActionCard("plus", t("start.new"), t("start.new_hint"), primary=True)
        self.open_button = ActionCard("folder", t("start.open"), t("start.open_hint"))
        actions.addWidget(self.new_button)
        actions.addWidget(self.open_button)
        outer.addLayout(actions)
        outer.addSpacing(40)

        outer.addWidget(eyebrow(t("start.recent")))
        outer.addSpacing(8)
        self.recent_list = QListWidget()
        self.recent_list.setIconSize(QSize(18, 18))
        self.recent_list.setObjectName("recent")
        self.recent_list.setFrameShape(QFrame.NoFrame)
        self.recent_list.setCursor(Qt.PointingHandCursor)
        self.recent_empty = QLabel(t("start.recent_empty"))
        self.recent_empty.setObjectName("muted")
        self.recent_empty.setContentsMargins(0, 12, 0, 0)
        outer.addWidget(self.recent_list)
        outer.addWidget(self.recent_empty)
        outer.addStretch(1)

        self.new_button.clicked.connect(self.create_requested)
        self.open_button.clicked.connect(self.open_requested)
        self.recent_list.itemActivated.connect(self._emit_recent)
        self.recent_list.itemClicked.connect(self._emit_recent)

    def _emit_recent(self, item: QListWidgetItem) -> None:
        self.recent_selected.emit(Path(item.data(Qt.UserRole)))

    def set_recent(self, paths: list[Path]) -> None:
        self.recent_list.clear()
        for path in paths:
            item = QListWidgetItem(icons.icon("folder", tokens()["muted"], 18), f"{path.name}\n{path.parent}")
            item.setData(Qt.UserRole, str(path))
            item.setToolTip(str(path))
            self.recent_list.addItem(item)
        self.recent_list.setVisible(bool(paths))
        self.recent_empty.setVisible(not paths)
        row = self.recent_list.sizeHintForRow(0) if paths else 0
        self.recent_list.setFixedHeight(min(len(paths), 6) * max(row, 52) + 4)
