"""Proje ekranı: 01 Dosyalar → 02 Kontrol → 03 Çıktı."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QListWidget, QMessageBox, QProgressBar,
    QPushButton, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from ..crypto_store import WrongPasswordError
from ..project import Project, ROLE_COUNTER, ROLE_MAIN
from .dialogs import NewPasswordDialog, PasswordPromptDialog
from .file_tree import DATA_ROLE, KIND_FILE, KIND_GROUP, KIND_ROLE, FileTree, _key
from .i18n import t
from .preflight import Blocker, collect_xlsx_report, preflight
from .result_dialog import open_folder, summarize
from . import icons
from .start_view import eyebrow
from .theme import tokens
from .widgets import FadeStack, ProgressRing, StepBar
from .workers import ClassifyWorker, ProcessWorker, start_worker

OUTPUT_FOLDER_NAME = "Siluet_Cikti"
STEPS = ("step.files", "step.review", "step.output")
# Kontrol listesi: (anahtar, bu maddeyi bozan engel kodları) — preflight sırasıyla aynı.
CHECKS = (
    ("check.roles", {"ambiguous_pending"}),
    ("check.files", {"no_files"}),
    ("check.sources", {"source_missing"}),
    ("check.names", {"duplicate_names"}),
    ("check.output", {"no_output", "output_inside_source", "output_not_writable"}),
    ("check.conflicts", {"output_exists"}),
)


def blocker_text(blocker: Blocker) -> str:
    return t(f"blocker.{blocker.code}", detail=blocker.detail) if blocker.detail else t(f"blocker.{blocker.code}", detail="")


class DropZone(QFrame):
    dropped = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("dropzone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(150)

    def _paths(self, event) -> list[Path]:
        return [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]

    def _set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self.isEnabled() and self._paths(event):
            self._set_active(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, _event) -> None:  # noqa: N802
        self._set_active(False)

    def dropEvent(self, event) -> None:  # noqa: N802
        self._set_active(False)
        paths = self._paths(event)
        if paths:
            event.acceptProposedAction()
            self.dropped.emit(paths)


class ProjectView(QWidget):
    close_requested = Signal()
    idle = Signal()
    busy_changed = Signal(bool)

    def __init__(self, project: Project, settings, parent: QWidget | None = None, state: dict | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("content")
        self.project = project
        self.settings = settings
        state = state or {}
        self.ambiguous: list = list(state.get("ambiguous", []))
        self.statuses: dict[str, str] = dict(state.get("statuses", {}))
        self.last_results = state.get("last_results")
        self.step = 0
        self._worker = None
        self._pending_notes: list[str] = []
        stored = settings.value(f"output/{project.project_id}", "")
        self.output_dir = Path(stored) if stored else project.path / OUTPUT_FOLDER_NAME
        self._build()
        self._set_banner(state.get("banner", ""))
        self.refresh()
        if self.last_results is not None:
            self._render_results(self.last_results)
        self.go_to_step(state.get("step", 0))

    def export_state(self) -> dict:
        """Dil/tema değişiminde görünüm yeniden kurulurken korunacak durum."""
        return {"ambiguous": self.ambiguous, "statuses": self.statuses, "step": self.step,
                "last_results": self.last_results, "banner": self.banner.text()}

    # -- değiştirilebilir etkileşim noktaları --
    def inform(self, title: str, text: str, level: str = "info") -> None:
        box = {"warning": QMessageBox.warning, "error": QMessageBox.critical}.get(level, QMessageBox.information)
        box(self, title, text)

    def ask_text(self, title: str, label: str, default: str = "") -> str | None:
        text, ok = QInputDialog.getText(self, title, label, text=default)
        return text.strip() if ok and text.strip() else None

    def show_result(self, results, output_dir: Path) -> None:
        self._render_results(results)

    # -- kurulum --
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 26, 32, 22)
        layout.setSpacing(0)
        self.step_bar = StepBar([t(key) for key in STEPS])
        self.step_bar.selected.connect(self._on_step_selected)
        layout.addWidget(self.step_bar)
        layout.addSpacing(22)
        self.pages = FadeStack()
        self.pages.addWidget(self._build_files_page())
        self.pages.addWidget(self._build_review_page())
        self.pages.addWidget(self._build_run_page())
        layout.addWidget(self.pages, 1)
        self.setAcceptDrops(True)
        self._editing_widgets = [self.add_button, self.add_folder_button, self.drop_zone, self.output_button]

    def _build_files_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        tok = tokens()
        self.drop_zone = DropZone()
        zone = QHBoxLayout(self.drop_zone)
        zone.setContentsMargins(26, 22, 26, 22)
        zone.setSpacing(20)
        tile = QLabel()
        tile.setFixedSize(56, 56)
        tile.setAlignment(Qt.AlignCenter)
        tile.setPixmap(icons.pixmap("upload", tok["accent"], 24))
        tile.setStyleSheet(f"background: {tok['accent_soft']}; border-radius: 18px;")
        zone.addWidget(tile, 0, Qt.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(4)
        title = QLabel(t("files.drop_title"))
        title.setObjectName("h1")
        hint = QLabel(t("files.drop_hint"))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        text.addStretch(1)
        text.addWidget(title)
        text.addWidget(hint)
        text.addStretch(1)
        zone.addLayout(text, 1)
        self.add_button = QPushButton(t("files.choose_files"))
        self.add_button.setIcon(icons.icon("file", tok["ink"], 16))
        self.add_folder_button = QPushButton(t("files.choose_folder"))
        self.add_folder_button.setIcon(icons.icon("folder", tok["ink"], 16))
        for button in (self.add_button, self.add_folder_button):
            button.setCursor(Qt.PointingHandCursor)
            zone.addWidget(button, 0, Qt.AlignVCenter)
        layout.addWidget(self.drop_zone)

        banner_row = QHBoxLayout()
        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner_close = QToolButton()
        self.banner_close.setIcon(icons.icon("close", tok["muted"], 16))
        self.banner_close.setAutoRaise(True)
        banner_row.addWidget(self.banner, 1)
        banner_row.addWidget(self.banner_close, 0, Qt.AlignTop)
        layout.addLayout(banner_row)

        list_card = QFrame()
        list_card.setObjectName("list_card")
        card_layout = QVBoxLayout(list_card)
        card_layout.setContentsMargins(10, 6, 10, 6)
        self.tree = FileTree()
        card_layout.addWidget(self.tree, 1)
        self.tree_empty = QLabel(t("files.empty"))
        self.tree_empty.setObjectName("muted")
        self.tree_empty.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.tree_empty, 1)
        layout.addWidget(list_card, 1)

        footer = QHBoxLayout()
        tree_hint = QLabel(t("files.tree_hint"))
        tree_hint.setObjectName("hint")
        tree_hint.setWordWrap(True)
        footer.addWidget(tree_hint, 1)
        self.files_status = QLabel()
        self.files_status.setObjectName("warning")
        footer.addWidget(self.files_status)
        self.next_button = QPushButton(t("step.next"))
        self.next_button.setObjectName("primary")
        self.next_button.setIcon(icons.icon("arrow_right", tok["on_accent"], 16))
        self.next_button.setLayoutDirection(Qt.RightToLeft)
        self.next_button.setCursor(Qt.PointingHandCursor)
        footer.addWidget(self.next_button)
        layout.addLayout(footer)

        self.drop_zone.dropped.connect(self.add_paths)
        self.add_button.clicked.connect(self._choose_files)
        self.add_folder_button.clicked.connect(self._choose_folder)
        self.banner_close.clicked.connect(lambda: self._set_banner(""))
        self.next_button.clicked.connect(lambda: self.go_to_step(1))
        self.tree.role_changed.connect(self._on_role_changed)
        self.tree.ambiguous_resolved.connect(self.resolve_ambiguous)
        self.tree.move_requested.connect(self._on_move_requested)
        self.tree.context_requested.connect(self._fill_context_menu)
        return page

    def _build_review_page(self) -> QWidget:
        tok = tokens()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(eyebrow(t("review.eyebrow")))
        layout.addSpacing(10)
        stats = QGridLayout()
        stats.setHorizontalSpacing(12)
        self.stat_labels: dict[str, QLabel] = {}
        for column, (key, label_key) in enumerate((("groups", "review.groups"), ("pairs", "review.pairs"),
                                                    ("singles", "review.singles"), ("files", "review.files"))):
            cell = QFrame()
            cell.setObjectName("card")
            box = QVBoxLayout(cell)
            box.setContentsMargins(20, 16, 20, 16)
            value = QLabel("0")
            value.setObjectName("stat")
            caption = QLabel(t(label_key).upper())
            caption.setObjectName("stat_label")
            box.addWidget(value)
            box.addWidget(caption)
            self.stat_labels[key] = value
            stats.addWidget(cell, 0, column)
        layout.addLayout(stats)
        layout.addSpacing(28)

        layout.addWidget(eyebrow(t("review.output")))
        layout.addSpacing(8)
        output_card = QFrame()
        output_card.setObjectName("card")
        output_row = QHBoxLayout(output_card)
        output_row.setContentsMargins(16, 12, 12, 12)
        output_row.setSpacing(10)
        folder_icon = QLabel()
        folder_icon.setPixmap(icons.pixmap("folder", tok["muted"], 18))
        output_row.addWidget(folder_icon)
        self.output_label = QLabel()
        self.output_label.setObjectName("mono")
        self.output_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        output_row.addWidget(self.output_label, 1)
        self.output_button = QPushButton(t("review.change"))
        self.open_output_button = QPushButton(t("review.open"))
        output_row.addWidget(self.output_button)
        output_row.addWidget(self.open_output_button)
        layout.addWidget(output_card)
        layout.addSpacing(28)

        layout.addWidget(eyebrow(t("review.checks")))
        layout.addSpacing(8)
        checks_card = QFrame()
        checks_card.setObjectName("card")
        checks = QGridLayout(checks_card)
        checks.setContentsMargins(18, 10, 18, 10)
        checks.setHorizontalSpacing(24)
        checks.setVerticalSpacing(0)
        self.check_rows: list[tuple[QLabel, QLabel]] = []
        for index, (key, _codes) in enumerate(CHECKS):
            row = QHBoxLayout()
            row.setContentsMargins(0, 8, 0, 8)
            row.setSpacing(10)
            mark = QLabel()
            mark.setFixedSize(24, 24)
            mark.setAlignment(Qt.AlignCenter)
            text = QLabel(t(key))
            row.addWidget(mark)
            row.addWidget(text, 1)
            checks.addLayout(row, index % 3, index // 3)
            self.check_rows.append((mark, text))
        layout.addWidget(checks_card)
        layout.addSpacing(14)
        self.blocker_label = QLabel()
        self.blocker_label.setObjectName("warning")
        self.blocker_label.setWordWrap(True)
        layout.addWidget(self.blocker_label)
        layout.addStretch(1)

        footer = QHBoxLayout()
        self.back_button = QPushButton(t("step.back"))
        self.back_button.setIcon(icons.icon("arrow_left", tok["ink"], 16))
        self.back_button.setCursor(Qt.PointingHandCursor)
        footer.addWidget(self.back_button)
        footer.addStretch(1)
        self.start_button = QPushButton(t("run.start"))
        self.start_button.setObjectName("primary")
        self.start_button.setMinimumWidth(180)
        self.start_button.setIcon(icons.icon("lock", tok["on_accent"], 16))
        self.start_button.setCursor(Qt.PointingHandCursor)
        footer.addWidget(self.start_button)
        layout.addLayout(footer)

        self.output_button.clicked.connect(self._choose_output)
        self.open_output_button.clicked.connect(self._open_output)
        self.back_button.clicked.connect(lambda: self.go_to_step(0))
        self.start_button.clicked.connect(self.start)
        return page

    def _build_run_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.run_stack = QStackedWidget()

        progress_page = QWidget()
        progress = QVBoxLayout(progress_page)
        progress.setContentsMargins(0, 0, 0, 0)
        progress.addWidget(eyebrow(t("run.working")))
        progress.addStretch(1)
        self.ring = ProgressRing()
        progress.addWidget(self.ring, 0, Qt.AlignHCenter)
        progress.addSpacing(18)
        self.counter_label = QLabel("00 / 00")
        self.counter_label.setObjectName("h1")
        self.counter_label.setAlignment(Qt.AlignCenter)
        progress.addWidget(self.counter_label)
        self.status_label = QLabel(t("status.ready"))
        self.status_label.setObjectName("mono")
        self.status_label.setAlignment(Qt.AlignCenter)
        progress.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()  # durum ProgressRing'de; değerler testler ve erişilebilirlik için tutulur
        progress.addWidget(self.progress)
        progress.addStretch(2)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_button = QPushButton(t("run.cancel"))
        row.addWidget(self.cancel_button)
        progress.addLayout(row)
        self.run_stack.addWidget(progress_page)

        result_page = QWidget()
        result = QVBoxLayout(result_page)
        result.setContentsMargins(0, 0, 0, 0)
        result.setSpacing(0)
        title_row = QHBoxLayout()
        title_row.setSpacing(16)
        self.result_tile = QLabel()
        self.result_tile.setFixedSize(56, 56)
        self.result_tile.setAlignment(Qt.AlignCenter)
        title_row.addWidget(self.result_tile)
        self.result_title = QLabel()
        self.result_title.setObjectName("display")
        title_row.addWidget(self.result_title, 1)
        result.addLayout(title_row)
        result.addSpacing(22)
        numbers = QGridLayout()
        numbers.setHorizontalSpacing(12)
        self.result_ok = QLabel("0")
        self.result_failed = QLabel("0")
        for column, (value, key) in enumerate(((self.result_ok, "run.ok"), (self.result_failed, "run.failed"))):
            cell = QFrame()
            cell.setObjectName("card")
            box = QVBoxLayout(cell)
            box.setContentsMargins(20, 16, 20, 16)
            value.setObjectName("stat")
            caption = QLabel(t(key).upper())
            caption.setObjectName("stat_label")
            box.addWidget(value)
            box.addWidget(caption)
            numbers.addWidget(cell, 0, column)
        result.addLayout(numbers)
        result.addSpacing(18)
        self.result_where = QLabel()
        self.result_where.setObjectName("mono")
        self.result_where.setWordWrap(True)
        result.addWidget(self.result_where)
        result.addSpacing(18)
        self.failed_caption = eyebrow(t("run.failed_list"))
        result.addWidget(self.failed_caption)
        result.addSpacing(6)
        self.failed_list = QListWidget()
        result.addWidget(self.failed_list, 1)
        result.addStretch(1)
        actions = QHBoxLayout()
        self.new_run_button = QPushButton(t("run.new"))
        self.new_run_button.setIcon(icons.icon("plus", tokens()["ink"], 16))
        actions.addWidget(self.new_run_button)
        actions.addStretch(1)
        self.open_result_button = QPushButton(t("run.open_output"))
        self.open_result_button.setObjectName("primary")
        self.open_result_button.setIcon(icons.icon("folder", tokens()["on_accent"], 16))
        actions.addWidget(self.open_result_button)
        result.addLayout(actions)
        self.run_stack.addWidget(result_page)

        layout.addWidget(self.run_stack, 1)
        self.cancel_button.clicked.connect(self.cancel)
        self.new_run_button.clicked.connect(self._new_run)
        self.open_result_button.clicked.connect(self._open_output)
        return page

    # -- adımlar --
    def _reachable_step(self) -> int:
        if self.is_busy() and self._worker_kind == "process":
            return 2
        if self.last_results is not None:
            return 2
        has_files = any(g.files for g in self.project.groups)
        return 1 if has_files and not self.ambiguous else 0

    def go_to_step(self, index: int) -> None:
        if self.is_busy() and self._worker_kind == "process":
            index = 2
        index = max(0, min(index, self._reachable_step() if index != 2 or self.last_results is None else 2))
        self.step = index
        self.pages.setCurrentIndex(index)
        self.step_bar.update_state(index, self._reachable_step())

    @Slot(int)
    def _on_step_selected(self, index: int) -> None:
        if not self.is_busy():
            self.go_to_step(index)

    def _new_run(self) -> None:
        self.last_results = None
        self.go_to_step(0)

    # -- durum --
    _worker_kind = ""

    def is_busy(self) -> bool:
        return self._worker is not None

    def blockers(self) -> list[Blocker]:
        return preflight(self.project, self.output_dir, len(self.ambiguous))

    def refresh(self) -> None:
        busy = self.is_busy()
        self.tree.editable = not busy
        self.tree.populate(self.project, self.ambiguous, self.statuses)
        has_rows = self.tree.topLevelItemCount() > 0
        self.tree.setVisible(has_rows)
        self.tree_empty.setVisible(not has_rows)
        self.output_label.setText(str(self.output_dir))
        self.output_label.setToolTip(str(self.output_dir))
        for widget in self._editing_widgets:
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy and self._worker_kind == "process")
        self.open_output_button.setEnabled(self.output_dir.is_dir())
        groups = self.project.groups
        files = sum(len(g.files) for g in groups)
        pairs = sum(1 for g in groups if {e.role for e in g.files} == {ROLE_MAIN, ROLE_COUNTER})
        singles = sum(1 for g in groups if len(g.files) == 1)
        for key, value in (("groups", len([g for g in groups if g.files])), ("pairs", pairs), ("singles", singles), ("files", files)):
            self.stat_labels[key].setText(str(value))
        blockers = [] if busy else self.blockers()
        codes = {b.code for b in blockers}
        failed_seen = False
        tok = tokens()
        for (mark, text), (_key_name, check_codes) in zip(self.check_rows, CHECKS):
            if codes & check_codes:
                name, fg, bg = "cross", tok["accent"], tok["accent_soft"]
                failed_seen = True
            elif failed_seen or busy:
                name, fg, bg = "dash", tok["faint"], tok["sunken"]
            else:
                name, fg, bg = "check", tok["ok"], tok["ok_soft"]
            mark.setPixmap(icons.pixmap(name, fg, 14))
            mark.setStyleSheet(f"background: {bg}; border-radius: 12px;")
        self.blocker_label.setText(blocker_text(blockers[0]) if blockers else ("" if busy else t("review.ready")))
        self.blocker_label.setObjectName("warning" if blockers else "muted")
        self.blocker_label.style().unpolish(self.blocker_label)
        self.blocker_label.style().polish(self.blocker_label)
        self.start_button.setEnabled(not busy and not blockers)
        files_blocked = (not busy) and (not files or bool(self.ambiguous))
        self.next_button.setEnabled(not busy and not files_blocked)
        if self.ambiguous:
            self.files_status.setText(blocker_text(Blocker("ambiguous_pending", "", str(len(self.ambiguous)))))
        else:
            self.files_status.setText("")
        self.back_button.setEnabled(not busy)
        self.step_bar.update_state(self.step, self._reachable_step())

    def _set_banner(self, text: str) -> None:
        self.banner.setText(text)
        self.banner.setVisible(bool(text))
        self.banner_close.setVisible(bool(text))

    def _guard(self, action) -> None:
        """Proje işlemlerini yürütür; hata olursa güvenli mesaj gösterir ve görünümü tazeler."""
        try:
            action()
        except Exception as exc:  # noqa: BLE001
            self.inform(t("dlg.action_failed"), str(exc) if isinstance(exc, (ValueError, KeyError)) else
                        t("err.unexpected", name=type(exc).__name__), "warning")
        self.refresh()

    # -- dosya ekleme --
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if not self.is_busy() and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.add_paths(paths)

    def _choose_files(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(self, t("files.dialog_files"), "", "Excel (*.xlsx)")
        if names:
            self.add_paths([Path(n) for n in names])

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("files.dialog_folder"))
        if folder:
            self.add_paths([Path(folder)])

    def add_paths(self, paths: list[Path]) -> None:
        if self.is_busy():
            return
        self.go_to_step(0)
        report = collect_xlsx_report(paths)
        known = {_key(e.path) for g in self.project.groups for e in g.files} | {_key(p.path) for p in self.ambiguous}
        new = [p for p in report.files if _key(p) not in known]
        notes = []
        if report.skipped_files:
            notes.append(t("banner.skipped_files", count=report.skipped_files))
        if report.skipped_folders:
            notes.append(t("banner.skipped_folders", count=report.skipped_folders))
        if report.unreadable:
            notes.append(t("banner.unreadable_folders", names=", ".join(p.name for p in report.unreadable[:3])))
        if report.files and not new:
            notes.append(t("banner.all_known"))
        if not new:
            self._set_banner(" ".join(notes) or t("banner.no_xlsx"))
            self.refresh()
            return
        self._pending_notes = notes
        worker = ClassifyWorker(new)
        worker.progress.connect(self._on_classify_progress)
        worker.finished.connect(self.apply_classification)
        worker.failed.connect(self._on_classify_failed)
        worker.cancelled.connect(self._on_classify_cancelled)
        self._begin_worker(worker, len(new), "classify")

    @Slot(int, int, str)
    def _on_classify_progress(self, done: int, total: int, name: str) -> None:
        self._set_banner(t("banner.inspecting", name=name) + f"  ({done}/{total})")

    @Slot(str)
    def _on_classify_failed(self, message: str) -> None:
        self._set_banner(t("status.classify_failed", error=message))
        self._finish_worker()

    @Slot()
    def _on_classify_cancelled(self) -> None:
        self._set_banner(t("status.classify_cancelled"))
        self._finish_worker()

    @Slot(object)
    def apply_classification(self, result) -> None:
        groups, ambiguous, failures = result
        notes = list(self._pending_notes)
        self._pending_notes = []
        try:
            added = self.project.add_auto_groups(groups)
        except Exception as exc:  # noqa: BLE001
            added = 0
            notes.append(t("banner.save_failed", error=type(exc).__name__))
        known = {_key(p.path) for p in self.ambiguous}
        self.ambiguous.extend(p for p in ambiguous if _key(p.path) not in known)
        if added:
            notes.insert(0, t("banner.added", count=added))
        if ambiguous:
            notes.append(t("banner.ambiguous", count=len(ambiguous)))
        if failures:
            names = ", ".join(f.path.name for f in failures[:5]) + (f" (+{len(failures) - 5})" if len(failures) > 5 else "")
            notes.append(t("banner.failures", count=len(failures), names=names))
        self._set_banner(" ".join(notes))
        self._finish_worker()

    def resolve_ambiguous(self, path: Path, role: str) -> None:
        profile = next((p for p in self.ambiguous if _key(p.path) == _key(path)), None)
        if profile is None:
            return

        def action():
            group = self.project.add_group(self._next_group_name("Elle"))
            self.project.add_file(group.group_id, profile.path, role, profile.sheets)
            self.ambiguous.remove(profile)
        self._guard(action)

    def _next_group_name(self, prefix: str) -> str:
        used = {g.name.casefold() for g in self.project.groups}
        number = 1
        while f"{prefix} {number:03d}".casefold() in used:
            number += 1
        return f"{prefix} {number:03d}"

    # -- düzenleme --
    def _on_role_changed(self, path: Path, role: str) -> None:
        self._guard(lambda: self.project.set_file_role(path, role))

    def _on_move_requested(self, paths: list, group_id: str) -> None:
        def action():
            for path in paths:
                self.project.move_file(Path(path), group_id)
        self._guard(action)

    def move_to_new_group(self, paths: list[Path]) -> None:
        name = self.ask_text(t("prompt.new_group"), t("prompt.group_name"), self._next_group_name("Elle"))
        if not name:
            return

        def action():
            group = self.project.add_group(name)
            for path in paths:
                self.project.move_file(Path(path), group.group_id)
        self._guard(action)

    def remove_files(self, paths: list[Path]) -> None:
        def action():
            for path in paths:
                self.project.remove_file(Path(path))
                self.statuses.pop(_key(path), None)
        self._guard(action)

    def _rename_group(self, group_id: str) -> None:
        group = self.project.get_group(group_id)
        name = self.ask_text(t("prompt.rename_group"), t("prompt.new_name"), group.name)
        if name:
            self._guard(lambda: self.project.rename_group(group_id, name))

    def _fill_context_menu(self, menu, items) -> None:
        files = [Path(i.data(0, DATA_ROLE)) for i in items if i.data(0, KIND_ROLE) == KIND_FILE]
        groups = [i.data(0, DATA_ROLE) for i in items if i.data(0, KIND_ROLE) == KIND_GROUP]
        if files:
            menu.addAction(t("menu.remove"), lambda: self.remove_files(files))
            menu.addAction(t("menu.move_new"), lambda: self.move_to_new_group(files))
            move_menu = menu.addMenu(t("menu.move_to"))
            for group in self.project.groups:
                move_menu.addAction(group.name, lambda gid=group.group_id: self._on_move_requested(files, gid))
        if len(groups) == 1 and not files:
            group = self.project.get_group(groups[0])
            menu.addAction(t("menu.rename"), lambda: self._rename_group(group.group_id))
            delete = menu.addAction(t("menu.delete_group"), lambda: self._guard(lambda: self.project.delete_group(group.group_id)))
            delete.setEnabled(not group.files)
            if group.files:
                delete.setToolTip(t("menu.delete_group_tip"))

    # -- çıktı --
    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("review.dialog_output"), str(self.output_dir.parent))
        if folder:
            self.set_output_dir(Path(folder))

    def set_output_dir(self, folder: Path) -> None:
        self.output_dir = Path(folder)
        self.settings.setValue(f"output/{self.project.project_id}", str(self.output_dir))
        self.refresh()

    def _open_output(self) -> None:
        if self.output_dir.is_dir():
            open_folder(self.output_dir)

    # -- parola --
    def change_password(self) -> None:
        prompt = PasswordPromptDialog(self, t("pw.change_title"), self.project.path.name)
        while prompt.exec():
            old = prompt.password()
            dialog = NewPasswordDialog(self, t("pw.title_change"))
            if not dialog.exec():
                return
            try:
                self.project.change_password(old, dialog.password(), dialog.password())
            except WrongPasswordError:
                prompt.show_error(t("err.wrong_password"))
                continue
            except Exception as exc:  # noqa: BLE001
                self.inform(t("pw.change_failed"), t("err.unexpected", name=type(exc).__name__), "error")
                return
            self.inform(t("pw.changed_title"), t("pw.changed"))
            return

    # -- çalıştırma --
    def start(self) -> None:
        if self.is_busy():
            return
        if self.blockers():
            self.refresh()
            return
        total = sum(len(g.files) for g in self.project.groups)
        self.statuses.clear()
        self.last_results = None
        worker = ProcessWorker(self.project, self.output_dir)
        worker.progress.connect(self._on_process_progress)
        worker.finished.connect(self._on_processed)
        worker.failed.connect(self._on_process_failed)
        worker.cancelled.connect(self._on_process_cancelled)
        self.run_stack.setCurrentIndex(0)
        self.ring.set_progress(0, total)
        self.counter_label.setText(f"00 / {total:02d}")
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(0)
        self.status_label.setText(t("run.preparing"))
        self._begin_worker(worker, total, "process")
        self.go_to_step(2)

    @Slot(int, int, str, str)
    def _on_process_progress(self, done: int, total: int, _group: str, name: str) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(min(done, total))
        self.ring.set_progress(done, total)
        self.counter_label.setText(f"{done:02d} / {total:02d}")
        metrics = self.status_label.fontMetrics()
        self.status_label.setText(metrics.elidedText(name, Qt.ElideMiddle, max(self.status_label.width(), 240)))

    @Slot(str)
    def _on_process_failed(self, message: str) -> None:
        self.status_label.setText(message)
        self._finish_worker()
        self.go_to_step(1)
        self.inform(t("run.error_title"), message, "error")

    @Slot()
    def _on_process_cancelled(self) -> None:
        self._finish_worker()
        self.go_to_step(1)
        self._set_banner(t("run.cancelled"))
        self.blocker_label.setText(t("run.cancelled"))

    @Slot(object)
    def _on_processed(self, results) -> None:
        for result in results:
            for context in result.files:
                self.statuses[_key(context.source)] = (
                    "✓ " + t("status.done") if context.status == "başarılı"
                    else "✕ " + t("status.failed", reason=context.error_message or t("run.unprocessed")))
        self.last_results = results
        self._finish_worker()
        self.go_to_step(2)
        self.show_result(results, self.output_dir)

    def _render_results(self, results) -> None:
        ok, failed = summarize(results)
        tok = tokens()
        self.result_title.setText(t("run.done_title") if not failed else t("run.partial_title"))
        self.result_tile.setPixmap(icons.pixmap("check" if not failed else "cross", tok["ok"] if not failed else tok["accent"], 26))
        self.result_tile.setStyleSheet(f"background: {tok['ok_soft'] if not failed else tok['accent_soft']}; border-radius: 18px;")
        self.result_ok.setText(str(ok))
        self.result_failed.setText(str(len(failed)))
        self.result_where.setText(str(self.output_dir))
        self.failed_list.clear()
        for name, reason in failed:
            self.failed_list.addItem(f"{name} — {reason}")
        self.failed_list.setVisible(bool(failed))
        self.failed_caption.setVisible(bool(failed))
        self.run_stack.setCurrentIndex(1)

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.status_label.setText(t("run.cancelling"))
            self.cancel_button.setEnabled(False)

    def _begin_worker(self, worker, total: int, kind: str) -> None:
        self._worker = worker
        self._worker_kind = kind
        self.refresh()
        self.busy_changed.emit(True)
        start_worker(worker, None)

    def _finish_worker(self) -> None:
        self._worker = None
        self._worker_kind = ""
        self.refresh()
        self.busy_changed.emit(False)
        self.idle.emit()
