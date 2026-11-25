"""Demo verisiyle README ve site için ekran görüntüleri üretir.

Kullanım: QT_QPA_PLATFORM=offscreen python tools/screenshots.py docs/screenshots [light|dark]
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication, QHeaderView, QTableWidget, QTableWidgetItem, QWidget, QHBoxLayout, QLabel, QVBoxLayout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from siluet.ui import i18n  # noqa: E402
from siluet.ui.app import MainWindow  # noqa: E402
from siluet.ui.dialogs import NewPasswordDialog  # noqa: E402

PASSWORD = "demo-parolasi-2026"


class Settings(dict):
    def value(self, key, default=None):
        return self.get(key, default)

    def setValue(self, key, value):
        self[key] = value


def pump(ms: int = 250) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def before_after(original: Path, anonymized: Path, out: Path) -> None:
    """Aynı satırların kaynak ve çıktı hâlini yan yana gösterir."""
    from openpyxl import load_workbook
    src, dst = load_workbook(original).active, load_workbook(anonymized).active
    rows = [r for r in range(1, src.max_row + 1) if src.cell(r, 1).value == "SIRA NO"]
    header_row = rows[1]  # GSM görüşme tablosu
    columns = [2, 4, 5, 6, 8]
    holder = QWidget()
    holder.setObjectName("content")
    holder.setAutoFillBackground(True)
    layout = QHBoxLayout(holder)
    titles = ("KAYNAK", "SİLÜET ÇIKTISI") if i18n.language() == "tr" else ("SOURCE", "SILUET OUTPUT")
    for title, sheet in zip(titles, (src, dst)):
        box = QVBoxLayout()
        label = QLabel(title)
        label.setObjectName("eyebrow")
        box.addWidget(label)
        table = QTableWidget(6, len(columns))
        table.setHorizontalHeaderLabels([str(src.cell(header_row, c).value).replace(" (Diğer Numara)", "") for c in columns])
        for i in range(6):
            for j, c in enumerate(columns):
                table.setItem(i, j, QTableWidgetItem(str(sheet.cell(header_row + 1 + i, c).value or "")))
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setFocusPolicy(Qt.NoFocus)
        table.clearSelection()
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.resizeRowsToContents()
        height = table.horizontalHeader().height() + sum(table.rowHeight(i) for i in range(table.rowCount())) + 4
        table.setFixedSize(650, height)
        box.addWidget(table)
        layout.addLayout(box)
    holder.adjustSize()
    holder.show()
    pump(300)
    holder.grab().save(str(out))


def main() -> None:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
    theme = sys.argv[2] if len(sys.argv) > 2 else "light"
    language = sys.argv[3] if len(sys.argv) > 3 else "tr"
    out_dir.mkdir(parents=True, exist_ok=True)
    QApplication.instance() or QApplication([])
    suffix = f"-{language}-{theme}"

    work = Path(tempfile.gettempdir()) / "Siluet-Demo"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    data = work / "HTS-2099"
    shutil.copytree(ROOT / "examples" / "demo", data)
    window = MainWindow(settings=Settings(theme=theme, language=language))
    window.resize(1240, 800)
    window.show()
    for name in ("Inceleme-Mart", "Inceleme-Nisan"):
        (work / name).mkdir()
        window.recent.add(work / name)
    window._refresh_recent()
    pump()
    window.grab().save(str(out_dir / f"1-baslangic{suffix}.png"))

    dialog = NewPasswordDialog(window, i18n.t("pw.title_new"), i18n.t("pw.intro_new"))
    dialog.first.setText(PASSWORD)
    dialog.second.setText(PASSWORD)
    dialog.show()
    pump()
    dialog.grab().save(str(out_dir / f"2-parola{suffix}.png"))
    dialog.close()

    window.ask_directory = lambda _title: work / "Inceleme-Kasim"
    window.ask_new_password = lambda *_a: PASSWORD
    window.create_project()
    view = window.project_view
    view.add_paths([data])
    for _ in range(100):
        pump(100)
        if not view.is_busy():
            break
    pump()
    window.grab().save(str(out_dir / f"3-dosyalar{suffix}.png"))
    view.go_to_step(1)
    pump()
    window.grab().save(str(out_dir / f"4-kontrol{suffix}.png"))

    view.start()
    for _ in range(300):
        pump(100)
        if not view.is_busy():
            break
    pump()
    window.grab().save(str(out_dir / f"5-sonuc{suffix}.png"))

    before_after(data / "demo-1-a.xlsx", view.output_dir / "demo-1-a.xlsx", out_dir / f"6-once-sonra{suffix}.png")
    window.close_project()
    window.grab().save(str(out_dir / f"1-baslangic{suffix}.png"))
    print("Ekran görüntüleri:", out_dir)


if __name__ == "__main__":
    main()
