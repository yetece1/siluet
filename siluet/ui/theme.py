"""Görsel dil: mürekkep ve kâğıt.

Açık temada sıcak kâğıt zemin üzerine mürekkep, koyu temada tersi. Tek vurgu rengi
zinober; birincil eylemde, etkin adımda ve dikkat gerektiren yerde kullanılır. Derinlik
gölge veya gradyanla değil, üst üste binen yüzey tonlarıyla verilir.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
SANS = "IBM Plex Sans"
MONO = "IBM Plex Mono"

TOKENS: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#ebe8e2", "panel": "#f6f4ef", "surface": "#fbfaf7", "raised": "#ffffff", "sunken": "#e2ded6",
        "line": "#dcd6cc", "line_strong": "#bfb8ac",
        "ink": "#18171b", "muted": "#6c675f", "faint": "#a19b91",
        "accent": "#d4472a", "accent_hover": "#b93c22", "on_accent": "#ffffff", "accent_soft": "#f7e1d9",
        "ok": "#2f7a4f", "ok_soft": "#dcebe1", "selection": "#ece4d7",
    },
    "dark": {
        "bg": "#0d0d10", "panel": "#141418", "surface": "#18181d", "raised": "#1f1f25", "sunken": "#25252c",
        "line": "#2a2a31", "line_strong": "#3c3c45",
        "ink": "#ece8e1", "muted": "#908b84", "faint": "#5d5953",
        "accent": "#f0603f", "accent_hover": "#ff7959", "on_accent": "#111114", "accent_soft": "#33201b",
        "ok": "#6cc28a", "ok_soft": "#1b2a21", "selection": "#28241f",
    },
}

_CURRENT = {"mode": "light"}


def tokens() -> dict[str, str]:
    """Etkin temanın renk değerleri (özel çizilen bileşenler için)."""
    return TOKENS[_CURRENT["mode"]]


def current_mode() -> str:
    return _CURRENT["mode"]


STYLE = """
* {{ font-family: "{sans}"; }}
QWidget {{ color: {ink}; font-size: 10pt; }}
QMainWindow, QDialog, QWidget#content, QWidget#root {{ background: {bg}; }}
QToolTip {{ background: {raised}; color: {ink}; border: 1px solid {line}; border-radius: 6px; padding: 5px 8px; }}

/* Yüzen kenar çubuğu paneli */
QFrame#sidebar {{ background: {panel}; border: 1px solid {line}; border-radius: 18px; }}
QLabel#wordmark {{ font-size: 25pt; font-weight: 600; letter-spacing: -0.6px; }}
QLabel#tagline {{ color: {muted}; }}
QLabel#eyebrow {{ font-family: "{mono}"; font-size: 8pt; color: {muted}; letter-spacing: 1.4px; }}
QLabel#muted, QLabel#hint {{ color: {muted}; }}
QLabel#mono {{ font-family: "{mono}"; font-size: 9pt; color: {muted}; }}
QLabel#chip {{ font-family: "{mono}"; font-size: 8pt; color: {ok}; background: {ok_soft}; border-radius: 9px; padding: 3px 9px; }}
QLabel#how_num {{ font-family: "{mono}"; color: {accent}; font-size: 9pt; }}
QLabel#version {{ font-family: "{mono}"; font-size: 8pt; color: {faint}; }}
QFrame#rule {{ background: {line}; max-height: 1px; min-height: 1px; border: none; }}
QFrame#project_card {{ background: {surface}; border: 1px solid {line}; border-radius: 14px; }}

/* Başlıklar */
QLabel#display {{ font-size: 34pt; font-weight: 600; letter-spacing: -1.2px; }}
QLabel#h1 {{ font-size: 17pt; font-weight: 600; letter-spacing: -0.3px; }}
QLabel#h2 {{ font-size: 11.5pt; font-weight: 600; }}
QLabel#warning {{ color: {accent}; }}
QLabel#ok {{ color: {ok}; }}
QLabel#stat {{ font-family: "{mono}"; font-size: 28pt; font-weight: 500; }}
QLabel#stat_label {{ font-family: "{mono}"; font-size: 8pt; color: {muted}; letter-spacing: 1.4px; }}
QLabel#banner {{ background: {accent_soft}; border-radius: 10px; padding: 10px 14px; }}
QLabel#icon_tile {{ background: {sunken}; border-radius: 12px; }}

/* Düğmeler: hap biçimi */
QPushButton {{ background: {surface}; border: 1px solid {line_strong}; border-radius: 18px; padding: 8px 18px; min-height: 18px; }}
QPushButton:hover {{ border-color: {ink}; }}
QPushButton:pressed {{ background: {sunken}; }}
QPushButton:disabled {{ color: {faint}; border-color: {line}; background: transparent; }}
QPushButton#primary {{ background: {accent}; color: {on_accent}; border: 1px solid {accent}; font-weight: 600; padding: 10px 24px; border-radius: 20px; }}
QPushButton#primary:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton#primary:disabled {{ background: {sunken}; color: {faint}; border-color: {sunken}; }}
QPushButton#quiet {{ background: transparent; border: none; border-radius: 10px; color: {muted}; padding: 8px 10px; text-align: left; }}
QPushButton#quiet:hover {{ background: {sunken}; color: {ink}; }}
QPushButton#quiet:disabled {{ color: {faint}; }}
QWidget#lang_switch {{ background: {sunken}; border-radius: 16px; }}
QPushButton#lang {{ background: transparent; border: none; border-radius: 13px; padding: 4px 10px; font-family: "{mono}"; font-size: 8.5pt; color: {muted}; min-height: 18px; }}
QPushButton#lang:checked {{ background: {raised}; color: {ink}; }}
QPushButton#lang:hover:!checked {{ color: {ink}; }}
QPushButton#action_card {{ background: {surface}; border: 1px solid {line}; border-radius: 18px; padding: 0; text-align: left; min-height: 150px; }}
QPushButton#action_card:hover {{ border-color: {accent}; background: {raised}; }}
QToolButton {{ border: none; border-radius: 12px; padding: 4px; }}
QToolButton:hover {{ background: {sunken}; }}

/* Kartlar ve sürükle-bırak alanı */
QFrame#dropzone {{ border: 1.5px dashed {line_strong}; background: {surface}; border-radius: 20px; }}
QFrame#dropzone[active="true"] {{ border: 1.5px solid {accent}; background: {accent_soft}; }}
QFrame#card {{ border: 1px solid {line}; background: {surface}; border-radius: 16px; }}
QFrame#list_card {{ border: 1px solid {line}; background: {surface}; border-radius: 16px; }}

/* Listeler ve ağaç */
QTreeWidget, QListWidget {{ background: transparent; border: none; outline: 0; }}
QTreeWidget::item {{ padding: 7px 2px; border-radius: 8px; }}
QTreeWidget::item:hover {{ background: {raised}; }}
QTreeWidget::item:selected, QListWidget::item:selected {{ background: {selection}; color: {ink}; }}
QListWidget::item {{ padding: 6px 4px; }}
QListWidget#recent::item {{ padding: 12px 14px; border-radius: 12px; margin: 2px 0; }}
QListWidget#recent::item:hover {{ background: {raised}; }}
QHeaderView::section {{ background: transparent; color: {muted}; border: none; border-bottom: 1px solid {line}; padding: 8px 6px; font-family: "{mono}"; font-size: 8pt; }}
QComboBox {{ border: 1px solid {line}; border-radius: 8px; padding: 4px 10px; background: {raised}; min-width: 110px; }}
QComboBox:hover {{ border-color: {line_strong}; }}
QComboBox QAbstractItemView {{ background: {raised}; border: 1px solid {line}; border-radius: 8px; selection-background-color: {selection}; selection-color: {ink}; padding: 4px; }}
QLineEdit {{ border: 1px solid {line_strong}; border-radius: 12px; padding: 9px 12px; background: {raised}; selection-background-color: {accent}; }}
QLineEdit:focus {{ border-color: {accent}; }}
QMenu {{ background: {raised}; border: 1px solid {line}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {selection}; }}

/* İlerleme */
QProgressBar {{ border: none; background: {sunken}; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}

/* Kaydırma çubukları */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {line_strong}; min-height: 28px; border-radius: 3px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {line_strong}; min-width: 28px; border-radius: 3px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QMessageBox QLabel {{ min-width: 320px; }}
"""

_FONTS_LOADED = False


def load_fonts() -> None:
    global _FONTS_LOADED
    if _FONTS_LOADED:
        return
    for path in sorted(FONT_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(path))
    _FONTS_LOADED = True


def system_prefers_dark(app: QApplication) -> bool:
    try:
        from PySide6.QtCore import Qt
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return app.palette().window().color().lightness() < 128


def resolve_mode(app: QApplication, stored: str | None) -> str:
    if stored in TOKENS:
        return stored
    return "dark" if system_prefers_dark(app) else "light"


def palette_for(mode: str) -> QPalette:
    tok = TOKENS[mode]
    palette = QPalette()
    roles = {
        QPalette.Window: tok["bg"], QPalette.WindowText: tok["ink"], QPalette.Base: tok["surface"],
        QPalette.AlternateBase: tok["raised"], QPalette.Text: tok["ink"], QPalette.Button: tok["surface"],
        QPalette.Shadow: tok["line_strong"],
        QPalette.ButtonText: tok["ink"], QPalette.Highlight: tok["accent"], QPalette.HighlightedText: tok["on_accent"],
        QPalette.PlaceholderText: tok["faint"], QPalette.ToolTipBase: tok["raised"], QPalette.ToolTipText: tok["ink"],
        QPalette.Mid: tok["line_strong"], QPalette.Midlight: tok["line"], QPalette.Light: tok["raised"],
        QPalette.Dark: tok["line_strong"], QPalette.Link: tok["accent"], QPalette.BrightText: tok["accent"],
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(tok["faint"]))
    return palette


def apply_theme(app: QApplication, mode: str) -> None:
    _CURRENT["mode"] = mode
    load_fonts()
    app.setStyle("Fusion")
    font = QFont(SANS)
    font.setPointSizeF(10)
    app.setFont(font)
    app.setPalette(palette_for(mode))
    app.setStyleSheet(STYLE.format(sans=SANS, mono=MONO, **TOKENS[mode]))
