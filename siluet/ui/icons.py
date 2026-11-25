"""Kodla çizilen ince çizgi simgeler ve bayraklar.

Simgeler QPainter ile tema rengine göre çizilir; yazı tipi veya emoji desteğine
bağlı değildir, bu yüzden Windows ve Linux'ta aynı görünür.
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

ASSETS = Path(__file__).resolve().parent / "assets"


def _pen(color: QColor, size: float) -> QPen:
    pen = QPen(color, max(1.4, size / 14))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _draw(name: str, p: QPainter, s: float, color: QColor) -> None:
    p.setPen(_pen(color, s))
    p.setBrush(Qt.NoBrush)
    m = s * 0.18  # iç boşluk
    w = s - 2 * m
    if name == "sun":
        c = QPointF(s / 2, s / 2)
        p.drawEllipse(c, w * 0.22, w * 0.22)
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(c.x() + math.cos(a) * w * 0.36, c.y() + math.sin(a) * w * 0.36),
                       QPointF(c.x() + math.cos(a) * w * 0.48, c.y() + math.sin(a) * w * 0.48))
    elif name == "moon":
        path = QPainterPath()
        r = w * 0.42
        c = QPointF(s / 2, s / 2)
        outer = QPainterPath()
        outer.addEllipse(c, r, r)
        bite = QPainterPath()
        bite.addEllipse(QPointF(c.x() + r * 0.55, c.y() - r * 0.45), r * 0.85, r * 0.85)
        path = outer.subtracted(bite)
        p.drawPath(path)
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(m, m + w * 0.18)
        path.lineTo(m + w * 0.36, m + w * 0.18)
        path.lineTo(m + w * 0.46, m + w * 0.30)
        path.lineTo(m + w, m + w * 0.30)
        path.lineTo(m + w, m + w * 0.86)
        path.lineTo(m, m + w * 0.86)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "file":
        path = QPainterPath()
        path.moveTo(m + w * 0.15, m)
        path.lineTo(m + w * 0.62, m)
        path.lineTo(m + w * 0.85, m + w * 0.24)
        path.lineTo(m + w * 0.85, m + w)
        path.lineTo(m + w * 0.15, m + w)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(m + w * 0.32, m + w * 0.55), QPointF(m + w * 0.68, m + w * 0.55))
        p.drawLine(QPointF(m + w * 0.32, m + w * 0.74), QPointF(m + w * 0.60, m + w * 0.74))
    elif name == "lock":
        p.drawRoundedRect(QRectF(m + w * 0.12, m + w * 0.44, w * 0.76, w * 0.56), w * 0.10, w * 0.10)
        path = QPainterPath()
        path.moveTo(m + w * 0.28, m + w * 0.44)
        path.lineTo(m + w * 0.28, m + w * 0.30)
        path.arcTo(QRectF(m + w * 0.28, m, w * 0.44, w * 0.56), 180, -180)
        path.lineTo(m + w * 0.72, m + w * 0.44)
        p.drawPath(path)
    elif name == "check":
        path = QPainterPath()
        path.moveTo(m + w * 0.08, m + w * 0.52)
        path.lineTo(m + w * 0.38, m + w * 0.80)
        path.lineTo(m + w * 0.92, m + w * 0.20)
        p.drawPath(path)
    elif name == "cross":
        p.drawLine(QPointF(m + w * 0.18, m + w * 0.18), QPointF(m + w * 0.82, m + w * 0.82))
        p.drawLine(QPointF(m + w * 0.82, m + w * 0.18), QPointF(m + w * 0.18, m + w * 0.82))
    elif name == "dash":
        p.drawLine(QPointF(m + w * 0.25, s / 2), QPointF(m + w * 0.75, s / 2))
    elif name in {"arrow_right", "arrow_left"}:
        sign = 1 if name == "arrow_right" else -1
        cx = s / 2
        p.drawLine(QPointF(cx - sign * w * 0.40, s / 2), QPointF(cx + sign * w * 0.40, s / 2))
        p.drawLine(QPointF(cx + sign * w * 0.40, s / 2), QPointF(cx + sign * w * 0.10, s / 2 - w * 0.30))
        p.drawLine(QPointF(cx + sign * w * 0.40, s / 2), QPointF(cx + sign * w * 0.10, s / 2 + w * 0.30))
    elif name == "chevron":
        p.drawLine(QPointF(m + w * 0.38, m + w * 0.20), QPointF(m + w * 0.68, m + w * 0.50))
        p.drawLine(QPointF(m + w * 0.68, m + w * 0.50), QPointF(m + w * 0.38, m + w * 0.80))
    elif name == "plus":
        p.drawLine(QPointF(s / 2, m + w * 0.12), QPointF(s / 2, m + w * 0.88))
        p.drawLine(QPointF(m + w * 0.12, s / 2), QPointF(m + w * 0.88, s / 2))
    elif name == "upload":
        p.drawLine(QPointF(s / 2, m + w * 0.06), QPointF(s / 2, m + w * 0.62))
        p.drawLine(QPointF(s / 2, m + w * 0.06), QPointF(s / 2 - w * 0.24, m + w * 0.30))
        p.drawLine(QPointF(s / 2, m + w * 0.06), QPointF(s / 2 + w * 0.24, m + w * 0.30))
        path = QPainterPath()
        path.moveTo(m + w * 0.06, m + w * 0.62)
        path.lineTo(m + w * 0.06, m + w * 0.94)
        path.lineTo(m + w * 0.94, m + w * 0.94)
        path.lineTo(m + w * 0.94, m + w * 0.62)
        p.drawPath(path)
    elif name == "key":
        p.drawEllipse(QPointF(m + w * 0.30, m + w * 0.50), w * 0.20, w * 0.20)
        p.drawLine(QPointF(m + w * 0.50, m + w * 0.50), QPointF(m + w * 0.95, m + w * 0.50))
        p.drawLine(QPointF(m + w * 0.80, m + w * 0.50), QPointF(m + w * 0.80, m + w * 0.68))
        p.drawLine(QPointF(m + w * 0.94, m + w * 0.50), QPointF(m + w * 0.94, m + w * 0.64))
    elif name == "close":
        p.drawLine(QPointF(m + w * 0.30, m + w * 0.30), QPointF(m + w * 0.70, m + w * 0.70))
        p.drawLine(QPointF(m + w * 0.70, m + w * 0.30), QPointF(m + w * 0.30, m + w * 0.70))
    elif name == "logout":
        path = QPainterPath()
        path.moveTo(m + w * 0.55, m + w * 0.08)
        path.lineTo(m + w * 0.08, m + w * 0.08)
        path.lineTo(m + w * 0.08, m + w * 0.92)
        path.lineTo(m + w * 0.55, m + w * 0.92)
        p.drawPath(path)
        p.drawLine(QPointF(m + w * 0.40, s / 2), QPointF(m + w * 0.95, s / 2))
        p.drawLine(QPointF(m + w * 0.95, s / 2), QPointF(m + w * 0.75, s / 2 - w * 0.20))
        p.drawLine(QPointF(m + w * 0.95, s / 2), QPointF(m + w * 0.75, s / 2 + w * 0.20))
    else:
        raise KeyError(name)


NAMES = ("sun", "moon", "folder", "file", "lock", "check", "cross", "dash", "arrow_right", "arrow_left",
         "chevron", "plus", "upload", "key", "close", "logout")


def pixmap(name: str, color: str, size: int = 18, ratio: float = 2.0) -> QPixmap:
    px = QPixmap(int(size * ratio), int(size * ratio))
    px.fill(Qt.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(ratio, ratio)
    _draw(name, painter, float(size), QColor(color))
    painter.end()
    px.setDevicePixelRatio(ratio)
    return px


def icon(name: str, color: str, size: int = 18) -> QIcon:
    return QIcon(pixmap(name, color, size))


def flag(code: str, size: int = 18) -> QIcon:
    """Yuvarlak bayrak simgesi (assets/flag_<code>.png)."""
    path = ASSETS / f"flag_{code}.png"
    return QIcon(str(path)) if path.is_file() else QIcon()
