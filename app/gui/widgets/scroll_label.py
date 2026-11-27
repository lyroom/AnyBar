import time

from PySide6.QtCore import Qt, QTimer, QRect, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QTextLayout, QTextOption
from PySide6.QtWidgets import QWidget

TICK_MS = 16


class ScrollLabel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._font = QFont("Microsoft YaHei", 12)
        self._color = QColor("#FFFFFF")
        self._speed = 30.0
        self._gap = 90.0
        self._multiline = False
        self._paused = False
        self._hover_to_scroll = False
        self._offset = 0.0
        self._last_ts = None
        self._external_lines = None
        self._lyric_index = 0
        self._lyric_frac = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_text(self, text: str):
        if text != self._text:
            self._text = text or ""
            self._offset = 0.0
            self.update()

    def set_font(self, font: QFont):
        if font != self._font:
            self._font = font
            self.update()

    def set_color(self, color: str):
        c = QColor(color)
        if c != self._color:
            self._color = c
            self.update()

    def set_speed(self, px_per_sec: float):
        self._speed = max(1.0, float(px_per_sec))

    def set_gap(self, px: float):
        self._gap = max(10.0, float(px))

    def set_multiline(self, flag: bool):
        self._multiline = bool(flag)
        self._offset = 0.0
        self.update()

    def set_paused(self, flag: bool):
        self._paused = bool(flag)

    def set_hover_to_scroll(self, flag: bool):
        self._hover_to_scroll = bool(flag)
        if flag:
            self._paused = True
            self._offset = 0.0
            self.update()

    def set_external_lines(self, lines):
        self._external_lines = list(lines) if lines else None
        self._lyric_index = 0
        self._lyric_frac = 0.0
        self._offset = 0.0
        self.update()

    def set_lyric_progress(self, index: int, frac: float):
        self._lyric_index = index
        self._lyric_frac = min(1.0, max(0.0, frac))
        self.update()

    def _fm(self) -> QFontMetrics:
        return QFontMetrics(self._font)

    def _single_line_width(self) -> int:
        if self._external_lines:
            fm = self._fm()
            return max((fm.horizontalAdvance(l) for l in self._external_lines), default=0)
        return self._fm().horizontalAdvance(self._text)

    def _wrap_lines(self, width: int):
        fm = self._fm()
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAnywhere)
        layout = QTextLayout(self._text, self._font)
        layout.setTextOption(option)
        layout.beginLayout()
        lines = []
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            start = line.textStart()
            length = line.textLength()
            lines.append(self._text[start:start + length].strip())
        layout.endLayout()
        if not lines:
            lines = [self._text]
        return lines, fm

    def _loop_len(self) -> float:
        return self._single_line_width() + self._gap

    def _tick(self):
        now = time.monotonic()
        if self._last_ts is None:
            self._last_ts = now
            return
        dt = now - self._last_ts
        self._last_ts = now
        if self._external_lines is not None or self._paused:
            return
        if self._multiline:
            lines, fm = self._wrap_lines(max(1, self.width()))
            total_h = fm.height() * len(lines)
            if total_h > self.height():
                self._offset += self._speed * dt
                if self._offset >= total_h + self._gap:
                    self._offset = 0.0
            self.update()
            return
        if self._single_line_width() > self.width():
            self._offset = (self._offset + self._speed * dt) % self._loop_len()
        else:
            self._offset = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self._font)
        painter.setPen(self._color)
        rect = self.rect()
        if self._external_lines is not None:
            self._paint_lyric(painter, rect)
        elif self._multiline:
            self._paint_wrapped(painter, rect)
        else:
            self._paint_single(painter, rect)
        painter.end()

    def _paint_single(self, painter: QPainter, rect: QRect):
        fm = self._fm()
        text_w = self._single_line_width()
        y = rect.top() + (rect.height() + fm.ascent() - fm.descent()) // 2
        if text_w <= rect.width():
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._text)
            return
        total = self._loop_len()
        x = rect.left() - self._offset
        painter.setClipRect(rect)
        painter.drawText(int(x), y, self._text)
        painter.drawText(int(x + total), y, self._text)

    def _paint_wrapped(self, painter: QPainter, rect: QRect):
        lines, fm = self._wrap_lines(max(1, rect.width()))
        line_h = fm.height()
        total_h = line_h * len(lines)
        painter.setClipRect(rect)
        if total_h <= rect.height():
            y = rect.top()
            for ln in lines:
                painter.drawText(QRect(0, int(y), rect.width(), line_h), Qt.AlignmentFlag.AlignVCenter, ln)
                y += line_h
            return
        y = rect.top() - self._offset
        for ln in lines:
            if y + line_h >= rect.top():
                painter.drawText(QRect(0, int(y), rect.width(), line_h), Qt.AlignmentFlag.AlignVCenter, ln)
            y += line_h
            if y > rect.bottom():
                break
        y2 = y + self._gap
        if y2 < rect.bottom():
            for ln in lines:
                painter.drawText(QRect(0, int(y2), rect.width(), line_h), Qt.AlignmentFlag.AlignVCenter, ln)
                y2 += line_h
                if y2 > rect.bottom():
                    break

    def _paint_lyric(self, painter: QPainter, rect: QRect):
        lines = self._external_lines
        if not lines:
            return
        fm = self._fm()
        line_h = fm.height() + 4
        idx = min(self._lyric_index, len(lines) - 1)
        cur_y = rect.top() + (rect.height() - line_h) // 2
        painter.setClipRect(rect)
        cur_opacity = 1.0 - 0.6 * self._lyric_frac
        painter.setOpacity(max(0.25, cur_opacity))
        painter.drawText(QRect(0, int(cur_y - line_h * self._lyric_frac), rect.width(), line_h),
                         Qt.AlignmentFlag.AlignCenter, lines[idx])
        if idx + 1 < len(lines):
            painter.setOpacity(min(1.0, 0.4 + 0.6 * self._lyric_frac))
            painter.drawText(QRect(0, int(cur_y + line_h * (1.0 - self._lyric_frac)), rect.width(), line_h),
                             Qt.AlignmentFlag.AlignCenter, lines[idx + 1])
        painter.setOpacity(1.0)
    def enterEvent(self, event):
        if self._hover_to_scroll:
            self._paused = False
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._hover_to_scroll:
            self._paused = True
            self._offset = 0.0
            self.update()
        super().leaveEvent(event)