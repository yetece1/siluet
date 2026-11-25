"""Grup/çift ağacı: dosyalar, türleri ve durumları."""
from __future__ import annotations

import os
from functools import partial
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QHeaderView, QMenu, QTreeWidget, QTreeWidgetItem

from ..project import Project, ROLE_COUNTER, ROLE_MAIN
from . import icons
from .i18n import t
from .theme import tokens

KIND_GROUP, KIND_FILE, KIND_AMBIGUOUS_ROOT, KIND_AMBIGUOUS = range(4)
KIND_ROLE = Qt.UserRole
DATA_ROLE = Qt.UserRole + 1


def _key(path) -> str:
    return os.path.normcase(str(Path(path).resolve()))


class FileTree(QTreeWidget):
    role_changed = Signal(Path, str)
    ambiguous_resolved = Signal(Path, str)
    move_requested = Signal(list, str)          # [Path], hedef group_id
    context_requested = Signal(object, object)  # QMenu, seçili öğeler

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setColumnCount(4)
        self.setHeaderLabels([t("tree.file").upper(), t("tree.role").upper(), t("tree.sheets").upper(), t("tree.status").upper()])
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setRootIsDecorated(True)
        self.setIndentation(18)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self._file_items: dict[str, QTreeWidgetItem] = {}
        self._ambiguous_items: dict[str, QTreeWidgetItem] = {}
        self.editable = True

    # -- doldurma --
    def populate(self, project: Project, ambiguous: list, statuses: dict[str, str]) -> None:
        self.clear()
        self._file_items.clear()
        self._ambiguous_items.clear()
        if ambiguous:
            root = QTreeWidgetItem([t("tree.ambiguous", count=len(ambiguous)), "", "", t("tree.choose_role")])
            root.setData(0, KIND_ROLE, KIND_AMBIGUOUS_ROOT)
            root.setData(0, DATA_ROLE, "__ambiguous__")
            root.setFlags(Qt.ItemIsEnabled)
            self.addTopLevelItem(root)
            for profile in ambiguous:
                item = QTreeWidgetItem([profile.path.name, "", str(len(profile.sheets) or "—"), t("tree.waiting")])
                item.setData(0, KIND_ROLE, KIND_AMBIGUOUS)
                item.setData(0, DATA_ROLE, str(profile.path))
                item.setToolTip(0, str(profile.path))
                item.setFlags(Qt.ItemIsEnabled)
                root.addChild(item)
                combo = QComboBox()
                combo.addItem(t("tree.choose_role_item"), "")
                combo.addItem(t("role.main"), ROLE_MAIN)
                combo.addItem(t("role.counter"), ROLE_COUNTER)
                combo.setEnabled(self.editable)
                combo.currentIndexChanged.connect(partial(self._on_ambiguous_index, str(profile.path)))
                self.setItemWidget(item, 1, combo)
                self._ambiguous_items[_key(profile.path)] = item
            root.setExpanded(True)
        for group in project.groups:
            roles = sorted({entry.role for entry in group.files})
            kind = t("tree.pair") if roles == [ROLE_COUNTER, ROLE_MAIN] else (t("tree.single") if len(group.files) == 1 else "")
            summary = t("tree.files_count", count=len(group.files)) + (f" · {kind}" if kind else "")
            top = QTreeWidgetItem([group.name, "", "", summary])
            top.setData(0, KIND_ROLE, KIND_GROUP)
            top.setIcon(0, icons.icon("folder", tokens()["muted"], 16))
            top.setData(0, DATA_ROLE, group.group_id)
            top.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled)
            font = top.font(0)
            font.setBold(True)
            top.setFont(0, font)
            self.addTopLevelItem(top)
            for entry in group.files:
                path = Path(entry.path)
                status = statuses.get(_key(path)) or (t("tree.ready") if path.is_file() else "⚠ " + t("tree.missing"))
                child = QTreeWidgetItem([path.name, "", str(len(entry.sheets) or "—"), status])
                child.setData(0, KIND_ROLE, KIND_FILE)
                child.setIcon(0, icons.icon("file", tokens()["faint"], 16))
                child.setData(0, DATA_ROLE, str(path))
                child.setToolTip(0, str(path))
                child.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
                top.addChild(child)
                combo = QComboBox()
                for role in (ROLE_MAIN, ROLE_COUNTER):
                    combo.addItem(t("role.main" if role == ROLE_MAIN else "role.counter"), role)
                combo.setCurrentIndex(combo.findData(entry.role))
                combo.setEnabled(self.editable)
                combo.currentIndexChanged.connect(partial(self._on_role_index, str(path)))
                self.setItemWidget(child, 1, combo)
                self._file_items[_key(path)] = child
            top.setExpanded(True)

    # Açılır listeler kendilerini yakalamaz: döngüsel çöp üretmemek için yalnız yol ve dizin taşınır.
    _ROLE_BY_INDEX = (ROLE_MAIN, ROLE_COUNTER)
    _AMBIGUOUS_BY_INDEX = ("", ROLE_MAIN, ROLE_COUNTER)

    def _on_role_index(self, path: str, index: int) -> None:
        if 0 <= index < len(self._ROLE_BY_INDEX):
            self.role_changed.emit(Path(path), self._ROLE_BY_INDEX[index])

    def _on_ambiguous_index(self, path: str, index: int) -> None:
        if 0 < index < len(self._AMBIGUOUS_BY_INDEX):
            self.ambiguous_resolved.emit(Path(path), self._AMBIGUOUS_BY_INDEX[index])

    def file_item(self, path) -> QTreeWidgetItem | None:
        return self._file_items.get(_key(path))

    def ambiguous_item(self, path) -> QTreeWidgetItem | None:
        return self._ambiguous_items.get(_key(path))

    def selected_files(self) -> list[Path]:
        return [Path(item.data(0, DATA_ROLE)) for item in self.selectedItems() if item.data(0, KIND_ROLE) == KIND_FILE]

    def selected_group_ids(self) -> list[str]:
        return [item.data(0, DATA_ROLE) for item in self.selectedItems() if item.data(0, KIND_ROLE) == KIND_GROUP]

    # -- sürükle-bırak: öğeleri Qt taşımaz, proje taşır ve ağaç yeniden doldurulur --
    def dropEvent(self, event) -> None:  # noqa: N802
        if not self.editable:
            event.ignore()
            return
        target = self.itemAt(event.position().toPoint())
        if target is not None and target.data(0, KIND_ROLE) == KIND_FILE:
            target = target.parent()
        files = self.selected_files()
        if target is None or target.data(0, KIND_ROLE) != KIND_GROUP or not files:
            event.ignore()
            return
        event.setDropAction(Qt.IgnoreAction)
        event.accept()
        self.move_requested.emit(files, target.data(0, DATA_ROLE))

    def _context_menu(self, position) -> None:
        if not self.editable:
            return
        item = self.itemAt(position)
        if item is not None and not item.isSelected():
            self.clearSelection()
            item.setSelected(True)
        menu = QMenu(self)
        self.context_requested.emit(menu, self.selectedItems())
        if not menu.isEmpty():
            menu.exec(self.viewport().mapToGlobal(position))
