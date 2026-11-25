"""Özel çizilen arayüz parçaları: tema anahtarı, dil seçici, adım göstergesi, ilerleme halkası."""
from __future__ import annotations

from PySide6.QtCore import (
    Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QGraphicsOpacityEffect, QHBoxLayout, QPushButton, QSizePolicy, QStackedWidget,
    QWidget,
)

from . import icons
from .theme import MONO, SANS, tokens


class ThemeSwitch(QAbstractButton):
    """Güneş/ay simgeli, topuzu kayan tema anahtarı. checked = koyu tema."""

    def __init__(self, dark: bool, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(dark)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(64, 32)
        self._pos = 1.0 if dark else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, value: float) -> None:
        self._pos = value
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(64, 32)

    def paintEvent(self, _event) -> None:  # noqa: N802
        tok = tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor(tok["line_strong"]), 1))
        p.setBrush(QColor(tok["sunken"]))
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        size = 14
        p.drawPixmap(QPointF(10, (self.height() - size) / 2), icons.pixmap("sun", tok["muted"], size))
        p.drawPixmap(QPointF(self.width() - 10 - size, (self.height() - size) / 2), icons.pixmap("moon", tok["muted"], size))
        d = self.height() - 8
        x = 4 + self._pos * (self.width() - 8 - d)
        knob = QRectF(x, 4, d, d)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(tok["ink"]))
        p.drawEllipse(knob)
        glyph = "moon" if self._pos > 0.5 else "sun"
        p.drawPixmap(QPointF(knob.center().x() - 7, knob.center().y() - 7), icons.pixmap(glyph, tok["bg"], 14))


class LanguageSwitch(QWidget):
    """Bayraklı TR/EN seçici (hap biçiminde iki düğme)."""

    changed = Signal(str)

    def __init__(self, current: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("lang_switch")
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for code, label in (("tr", "TR"), ("en", "EN")):
            button = QPushButton(label)
            button.setObjectName("lang")
            button.setCheckable(True)
            button.setChecked(code == current)
            button.setIcon(icons.flag(code))
            button.setIconSize(QSize(16, 16))
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _c=False, c=code: self.changed.emit(c))
            self.group.addButton(button)
            layout.addWidget(button)
            self.buttons[code] = button


class StepBar(QWidget):
    """Numaralı daireler ve bağlantı çizgisiyle üç adımlı gösterge."""

    selected = Signal(int)

    def __init__(self, labels: list[str], parent=None) -> None:
        super().__init__(parent)
        self.labels = labels
        self.current = 0
        self.reachable = 0
        self.setFixedHeight(44)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._hover = -1

    def update_state(self, current: int, reachable: int) -> None:
        self.current, self.reachable = current, reachable
        self.update()

    def _slots(self) -> list[QRectF]:
        width = self.width() / len(self.labels)
        return [QRectF(i * width, 0, width, self.height()) for i in range(len(self.labels))]

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = next((i for i, r in enumerate(self._slots()) if r.contains(event.position())), -1)
        hover = index if 0 <= index <= self.reachable else -1
        self.setCursor(Qt.PointingHandCursor if hover >= 0 else Qt.ArrowCursor)
        if hover != self._hover:
            self._hover = hover
            self.update()

    def leaveEvent(self, _event) -> None:  # noqa: N802
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        for index, rect in enumerate(self._slots()):
            if rect.contains(event.position()) and index <= self.reachable and self.isEnabled():
                self.selected.emit(index)

    def paintEvent(self, _event) -> None:  # noqa: N802
        tok = tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        d = 28
        cy = self.height() / 2
        slots = self._slots()
        number_font = QFont(MONO)
        number_font.setPixelSize(12)
        number_font.setWeight(QFont.Medium)
        label_font = QFont(SANS)
        label_font.setPixelSize(13)
        label_font.setWeight(QFont.Medium)
        for index, rect in enumerate(slots):
            circle = QRectF(rect.left(), cy - d / 2, d, d)
            if index < len(slots) - 1:
                line_y = cy
                start = rect.left() + d + 12 + QFontMetricsF(label_font).horizontalAdvance(self.labels[index]) + 16
                p.setPen(QPen(QColor(tok["ink"] if index < self.current else tok["line_strong"]), 1.2))
                p.drawLine(QPointF(start, line_y), QPointF(slots[index + 1].left() - 12, line_y))
            if index == self.current:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(tok["accent"]))
                p.drawEllipse(circle)
                p.setPen(QColor(tok["on_accent"]))
                p.setFont(number_font)
                p.drawText(circle, Qt.AlignCenter, f"{index + 1}")
                text_color = tok["ink"]
            elif index < self.current:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(tok["ink"]))
                p.drawEllipse(circle)
                p.drawPixmap(QPointF(circle.center().x() - 7, circle.center().y() - 7), icons.pixmap("check", tok["bg"], 14))
                text_color = tok["ink"]
            else:
                hovered = index == self._hover
                p.setPen(QPen(QColor(tok["ink"] if hovered else tok["line_strong"]), 1.2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(circle.adjusted(0.6, 0.6, -0.6, -0.6))
                p.setPen(QColor(tok["muted"] if index <= self.reachable else tok["faint"]))
                p.setFont(number_font)
                p.drawText(circle, Qt.AlignCenter, f"{index + 1}")
                text_color = tok["muted"] if index <= self.reachable else tok["faint"]
            p.setPen(QColor(text_color))
            p.setFont(label_font)
            text_rect = QRectF(circle.right() + 12, 0, rect.width() - d - 12, self.height())
            p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.labels[index])


class ProgressRing(QWidget):
    """Ortasında yüzde yazan dairesel ilerleme göstergesi."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.value = 0
        self.maximum = 1
        self.caption = ""
        self.setFixedSize(220, 220)

    def set_progress(self, value: int, maximum: int, caption: str = "") -> None:
        self.value, self.maximum, self.caption = value, max(maximum, 1), caption
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        tok = tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        stroke = 10
        rect = QRectF(stroke / 2, stroke / 2, self.width() - stroke, self.height() - stroke)
        p.setPen(QPen(QColor(tok["sunken"]), stroke, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 0, 360 * 16)
        fraction = min(self.value / self.maximum, 1.0)
        if fraction > 0:
            p.setPen(QPen(QColor(tok["accent"]), stroke, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(rect, 90 * 16, int(-fraction * 360 * 16))
        big = QFont(MONO)
        big.setPixelSize(44)
        big.setWeight(QFont.Medium)
        p.setFont(big)
        p.setPen(QColor(tok["ink"]))
        p.drawText(QRectF(0, 0, self.width(), self.height() - 18), Qt.AlignCenter, f"{int(fraction * 100)}%")
        small = QFont(MONO)
        small.setPixelSize(12)
        p.setFont(small)
        p.setPen(QColor(tok["muted"]))
        p.drawText(QRectF(0, self.height() / 2 + 14, self.width(), 24), Qt.AlignCenter, self.caption)


class FadeStack(QStackedWidget):
    """Sayfa değişiminde kısa bir solma geçişi yapan yığın."""

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if index == self.currentIndex():
            return super().setCurrentIndex(index)
        super().setCurrentIndex(index)
        widget = self.currentWidget()
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", widget)
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda w=widget: w.setGraphicsEffect(None))
        anim.start()


class IconButton(QPushButton):
    """Simgeli düğme; simge tema rengine göre çizilir."""

    def __init__(self, text: str, icon_name: str, color_key: str = "ink", object_name: str = "", trailing: bool = False) -> None:
        super().__init__(text)
        if object_name:
            self.setObjectName(object_name)
        self.setIcon(icons.icon(icon_name, tokens()[color_key], 16))
        self.setIconSize(QSize(16, 16))
        if trailing:
            self.setLayoutDirection(Qt.RightToLeft)
        self.setCursor(Qt.PointingHandCursor)
