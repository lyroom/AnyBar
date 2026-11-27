"""app/gui/widgets/indicators.py — 数据可视化指示控件（液态进度条、圆环仪表盘、脉冲状态灯）"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPalette, QPen, QRadialGradient
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from app.styles import qss_engine, theme, tokens

from . import motion


def quota_level(frac: float) -> str:
    if frac >= 0.8:
        return "err"
    if frac > 0.5:
        return "info"
    return "ok"


class AnimatedProgressBar(QWidget):
    """iOS 轻拟物液态进度条：内凹阴影槽 + 立体玻璃高光胶囊 + 错峰入场扫出 + 单次柔光流光。"""

    def __init__(self, dark: bool = False, color: str | None = None,
                 scale: float = 1.0, height_log: float = 7.5,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        t = tokens.get_tokens(self._dark)
        self._color = QColor(color or t.warn_solid)
        self._ratio = 0.0
        self._tween = motion.ValueTween(0.0, tokens.MOTION["emphasis"],
                                        QEasingCurve.Type.OutCubic, parent=self)
        self._tween.changed.connect(lambda _v: self.update())
        self._sheen = motion.ValueTween(-0.35, 680, QEasingCurve.Type.InOutSine, parent=self)
        self._sheen.changed.connect(lambda _v: self.update())
        self._delay_timer = QTimer(self)
        self._delay_timer.setSingleShot(True)
        self._delay_timer.timeout.connect(self._run_entrance)

        h = max(6, tokens.spx(height_log, self._scale))
        self._bar_h = float(h)
        self.setFixedHeight(h + max(2, tokens.spx(2, self._scale)))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_ratio(self, ratio: float, animated: bool = True) -> None:
        clamped = max(0.0, min(1.0, float(ratio)))
        self._ratio = clamped
        self._delay_timer.stop()
        self._tween.animate_to(clamped, animate=bool(animated and self.isVisible()))
        self.update()

    def play_entrance(self, delay_ms: int = 0) -> None:
        """悬浮窗弹出后触发从 0 丝滑扫出到目标值，并伴随一道柔和玻璃高光扫过。"""
        self._delay_timer.stop()
        self._tween.set_immediate(0.0)
        self._sheen.set_immediate(-0.35)
        if delay_ms > 0:
            self._delay_timer.start(int(delay_ms))
        else:
            self._run_entrance()

    def stop_entrance(self) -> None:
        self._delay_timer.stop()
        self._tween.stop()
        self._sheen.stop()

    def _run_entrance(self) -> None:
        if not self.isVisible():
            return
        if self._ratio <= 0.002:
            return
        self._tween.animate_to(self._ratio, duration=520,
                               easing=QEasingCurve.Type.OutQuint, animate=True)
        self._sheen.set_immediate(-0.30)
        self._sheen.animate_to(1.30, duration=780,
                               easing=QEasingCurve.Type.InOutSine, animate=True)

    def hideEvent(self, event):
        self.stop_entrance()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.stop_entrance()
        super().closeEvent(event)

    def set_color(self, color: str | QColor) -> None:
        c = QColor(color)
        if c != self._color:
            self._color = c
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        h = self._bar_h
        w = float(self.width())
        y = (float(self.height()) - h) / 2.0
        r = h / 2.0
        track_rect = QRectF(0.0, y, w, h)

        track_grad = QLinearGradient(0.0, y, 0.0, y + h)
        if self._dark:
            track_grad.setColorAt(0.0, QColor(12, 15, 22, 220))
            track_grad.setColorAt(1.0, QColor(42, 48, 62, 210))
        else:
            track_grad.setColorAt(0.0, QColor(203, 213, 225, 215))
            track_grad.setColorAt(1.0, QColor(232, 238, 246, 235))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track_grad)
        p.drawRoundedRect(track_rect, r, r)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 42 if self._dark else 26), 0.8))
        p.drawRoundedRect(track_rect.adjusted(0.4, 0.4, -0.4, -0.4), max(1.0, r - 0.4), max(1.0, r - 0.4))

        disp = self._tween.value
        if disp > 0.002:
            fill_w = max(h, w * disp)
            fill_rect = QRectF(0.0, y, fill_w, h)

            grad = QLinearGradient(0.0, y, fill_w, y)
            grad.setColorAt(0.0, self._color.darker(106))
            grad.setColorAt(0.65, self._color)
            grad.setColorAt(1.0, self._color.lighter(118))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawRoundedRect(fill_rect, r, r)

            hl_h = max(1.5, h * 0.44)
            hl_rect = QRectF(1.0, y + 0.5, max(2.0, fill_w - 2.0), hl_h)
            hl_grad = QLinearGradient(0.0, hl_rect.top(), 0.0, hl_rect.bottom())
            hl_grad.setColorAt(0.0, QColor(255, 255, 255, 130 if not self._dark else 96))
            hl_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(hl_grad)
            p.drawRoundedRect(hl_rect, hl_h / 2.0, hl_h / 2.0)

            sh = self._sheen.value
            if -0.25 < sh < 1.25 and fill_w > h * 1.6:
                cx = fill_w * sh
                band = max(24.0 * self._scale, fill_w * 0.28)
                sg = QLinearGradient(cx - band, y, cx + band, y)
                sg.setColorAt(0.0, QColor(255, 255, 255, 0))
                sg.setColorAt(0.5, QColor(255, 255, 255, 135))
                sg.setColorAt(1.0, QColor(255, 255, 255, 0))
                p.setBrush(sg)
                p.drawRoundedRect(fill_rect, r, r)

            if 0.04 < disp < 0.995:
                tip_x = fill_w - r
                tip_y = y + r
                tip_glow = QRadialGradient(tip_x, tip_y, r * 1.35)
                tip_glow.setColorAt(0.0, QColor(255, 255, 255, 155))
                tip_glow.setColorAt(1.0, QColor(255, 255, 255, 0))
                p.setBrush(tip_glow)
                p.drawEllipse(QPointF(tip_x, tip_y), r * 1.1, r * 1.1)
        p.end()


class AnimatedCircularGauge(QWidget):
    """iOS 轻拟物圆环仪表盘：内凹环槽 + 渐变立体弧 + 端头微光 + 入场扫弧动画。"""

    def __init__(self, ratio: float = 0.0, center_text: str = "",
                 color: str | None = None, dark: bool = True,
                 scale: float = 1.0, diameter_log: float = 54.0,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self._ratio = max(0.0, min(1.0, float(ratio)))
        self._color = color
        self._tween = motion.ValueTween(self._ratio, tokens.MOTION["emphasis"],
                                        QEasingCurve.Type.OutCubic, parent=self)
        self._tween.changed.connect(lambda _v: self.update())
        self._delay_timer = QTimer(self)
        self._delay_timer.setSingleShot(True)
        self._delay_timer.timeout.connect(self._run_entrance)

        size = max(46, tokens.spx(diameter_log, self._scale))
        self.setFixedSize(size, size)

        self.val_lbl = QLabel(center_text, self)
        self.val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.val_lbl.setFont(theme.ui_font(12 * self._scale, weight=800, mono=True))
        self.val_lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._apply_val_color()
        self.val_lbl.setGeometry(0, 0, size, size)

    def _apply_val_color(self) -> None:
        t = tokens.get_tokens(self._dark)
        role = "danger" if self._ratio > 0.88 else "primary"
        qss_engine.set_role(self.val_lbl, role)
        pal = self.val_lbl.palette()
        pal.setColor(QPalette.ColorRole.WindowText, QColor(t.danger if self._ratio > 0.88 else t.text))
        self.val_lbl.setPalette(pal)

    def set_gauge_value(self, ratio: float, text: str, color: str | None = None) -> None:
        self._ratio = max(0.0, min(1.0, float(ratio)))
        self._delay_timer.stop()
        self.val_lbl.setText(text)
        self._apply_val_color()
        if color is not None:
            self._color = color
        self._tween.animate_to(self._ratio, animate=self.isVisible())
        self.update()

    def play_entrance(self, delay_ms: int = 0) -> None:
        self._delay_timer.stop()
        self._tween.set_immediate(0.0)
        if delay_ms > 0:
            self._delay_timer.start(int(delay_ms))
        else:
            self._run_entrance()

    def stop_entrance(self) -> None:
        self._delay_timer.stop()
        self._tween.stop()

    def _run_entrance(self) -> None:
        if not self.isVisible():
            return
        if self._ratio <= 0.002:
            return
        self._tween.animate_to(self._ratio, duration=540,
                               easing=QEasingCurve.Type.OutQuint, animate=True)

    def hideEvent(self, event):
        self.stop_entrance()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.stop_entrance()
        super().closeEvent(event)

    def paintEvent(self, event):
        t = tokens.get_tokens(self._dark)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = float(self.width()), float(self.height())
        cx, cy = w / 2.0, h / 2.0
        stroke_w = max(4.0, 4.8 * self._scale)
        rad = min(w, h) / 2.0 - stroke_w / 2.0 - 2.0 * self._scale
        rect = QRectF(cx - rad, cy - rad, 2.0 * rad, 2.0 * rad)

        track_pen = QPen(QColor(*t.track_alpha), stroke_w)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(track_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        disp = self._tween.value
        if disp > 0.004:
            deg = min(360.0, 360.0 * disp)
            span = int(round(deg * 16))
            base_c = QColor(self._color) if self._color else QColor(tokens.load_tier_color(self._ratio, self._dark))
            glow_c = QColor(base_c)
            glow_c.setAlpha(42 if self._dark else 30)
            glow_pen = QPen(glow_c, stroke_w + 2.4 * self._scale)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(glow_pen)
            p.drawArc(rect, 90 * 16, -span)

            arc_grad = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
            arc_grad.setColorAt(0.0, base_c.lighter(122))
            arc_grad.setColorAt(1.0, base_c.darker(106))
            arc_pen = QPen(arc_grad, stroke_w)
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(arc_pen)
            p.drawArc(rect, 90 * 16, -span)
        p.end()


class PulseStatusDot(QWidget):
    """拟真玻璃灯珠状态点：立体高光核心 + 柔和呼吸光晕与扩散波纹，隐藏立刻停表。"""

    def __init__(self, color: str, scale: float = 1.0, animated: bool = False,
                 urgent: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._color = QColor(color)
        self._scale = max(1.0, float(scale))
        self._animated = bool(animated)
        self._urgent = bool(urgent)
        self._t0 = time.monotonic()
        d = max(12, tokens.spx(13, self._scale))
        self.setFixedSize(d, d)

        self._timer: QTimer | None = None
        if self._animated:
            self._timer = QTimer(self)
            self._timer.setInterval(36)
            self._timer.timeout.connect(self._tick)

    def set_color(self, color: str | QColor) -> None:
        c = QColor(color)
        if c != self._color:
            self._color = c
            self.update()

    def set_urgent(self, urgent: bool) -> None:
        if bool(urgent) != self._urgent:
            self._urgent = bool(urgent)
            self.update()

    def _tick(self) -> None:
        if not self.isVisible() or self.parent() is None:
            if self._timer is not None and self._timer.isActive():
                self._timer.stop()
            return
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if self._animated and self._timer is not None and not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event):
        if self._timer is not None and self._timer.isActive():
            self._timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        if self._timer is not None and self._timer.isActive():
            self._timer.stop()
        super().closeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        elapsed = time.monotonic() - self._t0
        speed = 3.6 if self._urgent else 2.1
        pulse = 0.5 + 0.5 * math.sin(elapsed * speed) if self._animated else 0.5
        r_core = (2.8 + (0.28 * pulse if self._urgent else 0.0)) * self._scale
        r_glow = (4.6 + (1.7 if self._urgent else 1.2) * pulse) * self._scale

        glow = QRadialGradient(cx, cy, r_glow)
        a_peak = int((135 + 95 * pulse) if self._urgent else (90 + 75 * pulse)) if self._animated else 95
        glow.setColorAt(0.0, QColor(self._color.red(), self._color.green(), self._color.blue(), min(255, a_peak)))
        glow.setColorAt(1.0, QColor(self._color.red(), self._color.green(), self._color.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(cx, cy), r_glow, r_glow)

        if self._animated and self._urgent:
            wave = (elapsed * 0.85) % 1.0
            wr = r_core + wave * (3.6 * self._scale)
            wa = int(175 * (1.0 - wave))
            if wa > 8:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(self._color.red(), self._color.green(), self._color.blue(), wa), max(1.0, 1.1 * self._scale)))
                p.drawEllipse(QPointF(cx, cy), wr, wr)

        bead = QRadialGradient(cx - r_core * 0.30, cy - r_core * 0.30, r_core * 1.4)
        bead.setColorAt(0.0, self._color.lighter(155))
        bead.setColorAt(0.45, self._color)
        bead.setColorAt(1.0, self._color.darker(118))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bead)
        p.drawEllipse(QPointF(cx, cy), r_core, r_core)
        p.end()
