"""Uygulama giriş noktası ve ana pencere: kenar çubuğu + içerik alanı."""
from __future__ import annotations

import gc
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QTimer, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from ..crypto_store import CorruptProjectError, WrongPasswordError
from ..migration import BACKUP_NAME, leftover_backup, migrate_legacy, secure_delete
from ..project import PROJECT_FILE, Project, ProjectLockedError
from . import i18n
from .dialogs import NewPasswordDialog, PasswordPromptDialog
from .i18n import t
from .project_view import ProjectView
from .recent import RecentProjects
from .start_view import StartView, eyebrow
from . import icons
from .theme import apply_theme, resolve_mode, tokens
from .widgets import LanguageSwitch, ThemeSwitch

APP_NAME = "Silüet"
MIN_WIDTH, MIN_HEIGHT = 1040, 680
SIDEBAR_WIDTH = 276


def wordmark_html(accent: str) -> str:
    """Kelime işareti: küçük harfli "silüet"; yalnız ü harfi vurgu renginde."""
    return f'sil<span style="color:{accent}">ü</span>et'


class MainWindow(QMainWindow):
    def __init__(self, settings=None) -> None:
        super().__init__()
        self.settings = settings if settings is not None else QSettings("yetece", "Siluet")
        self.recent = RecentProjects(self.settings)
        self.project: Project | None = None
        self.project_view: ProjectView | None = None
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self.resize(1240, 800)
        i18n.set_language(str(self.settings.value("language", "tr") or "tr"))
        app = QApplication.instance()
        self.theme = resolve_mode(app, self.settings.value("theme", None))
        apply_theme(app, self.theme)
        self._build()

    # -- kurulum: dil veya tema değişince bütün arayüz yeniden kurulur --
    def _build(self, view_state: dict | None = None) -> None:
        root = QWidget()
        root.setObjectName("root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(12, 12, 0, 12)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        layout.addWidget(self.stack, 1)
        self.start_view = StartView()
        self.stack.addWidget(self.start_view)
        self.start_view.create_requested.connect(self.create_project)
        self.start_view.open_requested.connect(self.open_project)
        self.start_view.recent_selected.connect(self.open_path)
        old = self.centralWidget()
        self.setCentralWidget(root)
        if old is not None:
            old.deleteLater()
        self.project_view = None
        if self.project is not None:
            self._mount_project_view(view_state)
        self._refresh_recent()
        self._refresh_sidebar()

    def _build_sidebar(self) -> QFrame:
        tok = tokens()
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(22, 26, 22, 18)
        layout.setSpacing(0)
        mark_row = QHBoxLayout()
        mark_row.setSpacing(10)
        mark = QLabel(wordmark_html(tok["accent"]))
        mark.setObjectName("wordmark")
        mark.setTextFormat(Qt.RichText)
        mark_row.addWidget(mark)
        mark_row.addStretch(1)
        layout.addLayout(mark_row)
        layout.addSpacing(6)
        tagline = QLabel(t("app.tagline"))
        tagline.setObjectName("tagline")
        tagline.setWordWrap(True)
        layout.addWidget(tagline)
        layout.addSpacing(26)

        # Proje açıkken: kart (ad, yol, şifre durumu) ve eylemler
        self.sidebar_project_box = QWidget()
        box = QVBoxLayout(self.sidebar_project_box)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        box.addWidget(eyebrow(t("side.project")))
        card = QFrame()
        card.setObjectName("project_card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(10)
        tile = QLabel()
        tile.setObjectName("icon_tile")
        tile.setFixedSize(36, 36)
        tile.setAlignment(Qt.AlignCenter)
        tile.setPixmap(icons.pixmap("folder", tok["ink"], 18))
        head.addWidget(tile, 0, Qt.AlignTop)
        names = QVBoxLayout()
        names.setSpacing(2)
        self.sidebar_project_name = QLabel()
        self.sidebar_project_name.setObjectName("h2")
        self.sidebar_project_name.setWordWrap(True)
        names.addWidget(self.sidebar_project_name)
        self.sidebar_project_path = QLabel()
        self.sidebar_project_path.setObjectName("mono")
        self.sidebar_project_path.setWordWrap(True)
        names.addWidget(self.sidebar_project_path)
        head.addLayout(names, 1)
        card_layout.addLayout(head)
        card_layout.addSpacing(8)
        chip_row = QHBoxLayout()
        chip = QLabel("● " + t("side.encrypted"))
        chip.setObjectName("chip")
        chip_row.addWidget(chip)
        chip_row.addStretch(1)
        card_layout.addLayout(chip_row)
        box.addWidget(card)
        box.addSpacing(8)
        self.password_button = QPushButton(t("side.change_password"))
        self.password_button.setObjectName("quiet")
        self.password_button.setIcon(icons.icon("key", tok["muted"], 16))
        self.close_button = QPushButton(t("side.close_project"))
        self.close_button.setObjectName("quiet")
        self.close_button.setIcon(icons.icon("logout", tok["muted"], 16))
        for button in (self.password_button, self.close_button):
            button.setCursor(Qt.PointingHandCursor)
            box.addWidget(button)
        layout.addWidget(self.sidebar_project_box)

        # Proje yokken: nasıl çalışır
        self.sidebar_how_box = QWidget()
        how = QVBoxLayout(self.sidebar_how_box)
        how.setContentsMargins(0, 0, 0, 0)
        how.setSpacing(12)
        how.addWidget(eyebrow(t("side.how")))
        for number, key in (("01", "side.how1"), ("02", "side.how2"), ("03", "side.how3")):
            row = QHBoxLayout()
            row.setSpacing(12)
            num = QLabel(number)
            num.setObjectName("how_num")
            text = QLabel(t(key))
            text.setObjectName("muted")
            text.setWordWrap(True)
            row.addWidget(num, 0, Qt.AlignTop)
            row.addWidget(text, 1)
            how.addLayout(row)
        layout.addWidget(self.sidebar_how_box)
        layout.addStretch(1)

        toggles = QHBoxLayout()
        toggles.setSpacing(8)
        self.language_switch = LanguageSwitch(i18n.language())
        self.language_switch.changed.connect(self.set_language)
        self.lang_tr = self.language_switch.buttons["tr"]
        self.lang_en = self.language_switch.buttons["en"]
        toggles.addWidget(self.language_switch)
        toggles.addStretch(1)
        self.theme_button = ThemeSwitch(self.theme == "dark")
        self.theme_button.setToolTip(t("side.theme_light") if self.theme == "dark" else t("side.theme_dark"))
        self.theme_button.clicked.connect(self.toggle_theme)
        toggles.addWidget(self.theme_button)
        layout.addLayout(toggles)
        layout.addSpacing(14)
        version = QLabel(f"v{__version__} · {t('side.offline')}")
        version.setObjectName("version")
        layout.addWidget(version)

        self.password_button.clicked.connect(self._change_password)
        self.close_button.clicked.connect(self.close_project)
        return bar

    def _refresh_sidebar(self) -> None:
        has_project = self.project is not None
        self.sidebar_project_box.setVisible(has_project)
        self.sidebar_how_box.setVisible(not has_project)
        if has_project:
            self.sidebar_project_name.setText(self.project.path.name)
            self.sidebar_project_path.setText(str(self.project.path.parent))
            self.sidebar_project_path.setToolTip(str(self.project.path))
        self._set_toggles_enabled(not (self.project_view and self.project_view.is_busy()))

    def _set_toggles_enabled(self, enabled: bool) -> None:
        for widget in (self.language_switch, self.theme_button, self.close_button, self.password_button):
            widget.setEnabled(enabled)

    # -- dil ve tema --
    def set_language(self, code: str) -> None:
        if self.project_view is not None and self.project_view.is_busy():
            return
        self.settings.setValue("language", code)
        if code != i18n.language():
            i18n.set_language(code)
            self._rebuild()

    def toggle_theme(self) -> None:
        if self.project_view is not None and self.project_view.is_busy():
            return
        self.theme = "light" if self.theme == "dark" else "dark"
        self.settings.setValue("theme", self.theme)
        apply_theme(QApplication.instance(), self.theme)
        # Renkler hemen uygulanır; simgeler anahtarın kayma animasyonu bitince yeni renkle çizilir.
        QTimer.singleShot(240, self._rebuild)

    def _rebuild(self) -> None:
        state = self.project_view.export_state() if self.project_view is not None else None
        self._build(state)

    # -- değiştirilebilir etkileşim noktaları (testler bunları değiştirir) --
    def ask_directory(self, title: str) -> Path | None:
        chosen = QFileDialog.getExistingDirectory(self, title)
        return Path(chosen) if chosen else None

    def ask_new_password(self, title: str, intro: str = "") -> str | None:
        dialog = NewPasswordDialog(self, title, intro)
        return dialog.password() if dialog.exec() else None

    def ask_password(self, project_name: str, error: str | None) -> str | None:
        dialog = PasswordPromptDialog(self, t("pw.open_title"), project_name)
        if error:
            dialog.show_error(error)
        return dialog.password() if dialog.exec() else None

    def confirm(self, title: str, text: str) -> bool:
        box = QMessageBox(QMessageBox.Question, title, text, parent=self)
        yes = box.addButton(t("dlg.yes"), QMessageBox.YesRole)
        box.addButton(t("dlg.no"), QMessageBox.NoRole)
        box.setDefaultButton(yes)
        box.exec()
        return box.clickedButton() is yes

    def inform(self, title: str, text: str, level: str = "info") -> None:
        icon = {"warning": QMessageBox.Warning, "error": QMessageBox.Critical}.get(level, QMessageBox.Information)
        box = QMessageBox(icon, title, text, parent=self)
        box.addButton(t("pw.ok"), QMessageBox.AcceptRole)
        box.exec()

    # -- akışlar --
    def create_project(self) -> None:
        folder = self.ask_directory(t("dlg.choose_new_folder"))
        if folder is None:
            return
        if (folder / PROJECT_FILE).exists():
            self.inform(t("dlg.project_exists_title"), t("dlg.project_exists"), "warning")
            return
        password = self.ask_new_password(t("pw.title_new"), t("pw.intro_new"))
        if password is None:
            return
        try:
            project = Project.create(folder, password)
        except Exception as exc:  # noqa: BLE001
            self.inform(t("dlg.create_failed"), _message(exc), "error")
            return
        self._show_project(project)

    def open_project(self) -> None:
        folder = self.ask_directory(t("dlg.choose_project_folder"))
        if folder is not None:
            self.open_path(folder)

    def open_path(self, folder: Path) -> None:
        if self.project is not None:
            self.close_project()
            if self.project is not None:
                return
        try:
            version = Project.detect_version(folder)
        except Exception as exc:  # noqa: BLE001 - bozuk/okunamayan dosya sessizce yutulmasın
            self.inform(t("dlg.open_failed"), _message(exc), "error")
            return
        if version is None:
            self.recent.remove(folder)
            self._refresh_recent()
            self.inform(t("dlg.not_found_title"), t("dlg.not_found"), "warning")
            return
        if version in {1, 2}:
            self._migrate(folder)
            return
        error = None
        while True:
            password = self.ask_password(folder.name, error)
            if password is None:
                return
            try:
                project = Project.open(folder, password)
            except WrongPasswordError:
                error = t("err.wrong_password")
                continue
            except Exception as exc:  # noqa: BLE001
                self.inform(t("dlg.open_failed"), _message(exc), "error")
                return
            self._show_project(project)
            return

    def _migrate(self, folder: Path) -> None:
        if not self.confirm(t("dlg.migrate_title"), t("dlg.migrate")):
            return
        password = self.ask_new_password(t("pw.title_migrate"), t("pw.intro_migrate"))
        if password is None:
            return
        try:
            result = migrate_legacy(folder, password, password)
        except Exception as exc:  # noqa: BLE001
            self.inform(t("dlg.migrate_failed"), t("dlg.migrate_failed_detail", error=_message(exc)), "error")
            return
        try:
            secure_delete(result.backup_path)
        except OSError:
            pass  # _show_project kalan yedeği yeniden sorar
        self._show_project(result.project)

    def _offer_backup_cleanup(self, folder: Path) -> None:
        backup = leftover_backup(folder)
        if backup is None:
            return
        if self.confirm(t("dlg.backup_title"), t("dlg.backup", name=BACKUP_NAME)):
            try:
                secure_delete(backup)
            except OSError:
                self.inform(t("dlg.backup_failed_title"), t("dlg.backup_failed", name=BACKUP_NAME), "warning")

    def _show_project(self, project: Project) -> None:
        self._offer_backup_cleanup(project.path)
        self.project = project
        self.recent.add(project.path)
        self._mount_project_view(None)
        self._refresh_recent()
        self._refresh_sidebar()

    def _mount_project_view(self, state: dict | None) -> None:
        self.project_view = ProjectView(self.project, self.settings, self, state)
        self.project_view.close_requested.connect(self.close_project)
        self.project_view.busy_changed.connect(lambda busy: self._set_toggles_enabled(not busy))
        self.stack.addWidget(self.project_view)
        self.stack.setCurrentWidget(self.project_view)
        self.setWindowTitle(f"{APP_NAME} — {self.project.path.name}")

    def _change_password(self) -> None:
        if self.project_view is not None:
            self.project_view.change_password()

    def close_project(self) -> None:
        if self.project_view is not None and self.project_view.is_busy():
            self.inform(t("dlg.busy_title"), t("dlg.busy_close"), "warning")
            return
        if self.project_view is not None:
            self.stack.removeWidget(self.project_view)
            self.project_view.deleteLater()
            self.project_view = None
        if self.project is not None:
            self.project.close()
            self.project = None
        self.stack.setCurrentWidget(self.start_view)
        self.setWindowTitle(APP_NAME)
        self._refresh_recent()
        self._refresh_sidebar()

    def _refresh_recent(self) -> None:
        self.start_view.set_recent(self.recent.list())

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt adı
        view = self.project_view
        if view is not None and view.is_busy():
            if not self.confirm(t("dlg.busy_title"), t("dlg.busy_quit")):
                event.ignore()
                return
            view.cancel()
            view.idle.connect(self.close)
            event.ignore()
            return
        if self.project is not None:
            self.project.close()
            self.project = None
        event.accept()


def _message(exc: Exception) -> str:
    if isinstance(exc, WrongPasswordError):
        return t("err.wrong_password")
    if isinstance(exc, ProjectLockedError):
        return t("err.locked")
    if isinstance(exc, CorruptProjectError):
        return t("err.corrupt")
    if isinstance(exc, FileExistsError):
        return t("err.exists")
    if isinstance(exc, PermissionError):
        return t("err.permission")
    if type(exc) is ValueError and str(exc):
        return str(exc)
    return t("err.unexpected", name=type(exc).__name__)


class _MainThreadGarbageCollector(QObject):
    """Python'un döngüsel çöp toplayıcısını yalnız ana iş parçacığında çalıştırır.

    Otomatik toplama, bellek ayıran herhangi bir iş parçacığında (ör. openpyxl'in çalıştığı
    işçi) tetiklenebilir ve döngüdeki Qt nesnelerini yanlış iş parçacığında yok ederek
    çökmeye yol açar. Bu sınıf otomatik toplamayı kapatır, eşikleri bir zamanlayıcıyla
    ana iş parçacığında denetler.
    """

    INTERVAL_MS = 500

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self.threshold = gc.get_threshold()
        gc.disable()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)
        self.timer.start(self.INTERVAL_MS)

    @Slot()
    def check(self) -> None:
        counts = gc.get_count()
        if counts[0] > self.threshold[0]:
            generation = 0
            if counts[1] > self.threshold[1]:
                generation = 1
                if counts[2] > self.threshold[2]:
                    generation = 2
            gc.collect(generation)


def install_main_thread_gc(app: QApplication) -> QObject:
    existing = app.findChild(_MainThreadGarbageCollector)
    return existing if existing is not None else _MainThreadGarbageCollector(app)


def install_shutdown_hook(app: QApplication) -> None:
    """Uygulama kapanırken çalışan iş parçacıklarını bekler (yarıda yok edilmesinler)."""
    from .workers import wait_all
    app.aboutToQuit.connect(wait_all)


def main() -> int:
    from ..crash_log import install_crash_logging
    install_crash_logging(native_crashes=True)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("siluet")
    icon = Path(__file__).resolve().parent / "assets" / "icon.png"
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    install_shutdown_hook(app)
    install_main_thread_gc(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
