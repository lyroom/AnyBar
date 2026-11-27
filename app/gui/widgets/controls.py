"""app/gui/widgets/controls.py — 交互输入原子控件（开关、分段滑块、矢量图标按钮）"""

from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QPushButton, QSizePolicy, QWidget

from app.styles import icons, theme, tokens

from . import motion


class ToggleSwitch(QAbstractButton):
    """Fluent / HIG 现代滑块开关：阻尼平移动画 + 轨道色渐变 + 按压微拉伸。

    完整兼容 QCheckBox 常用 API（isChecked / setChecked / toggled / stateChanged）。
    """

    stateChanged = Signal(int)

    def __init__(self, text: str = "", dark: bool = False, scale: float = 1.0,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self._font = theme.ui_font(12.5 * self._scale, 500)
        self.setFont(self._font)
        self.setCheckable(True)
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._pos_tween = motion.ValueTween(0.0, tokens.MOTION["standard"],
                                            QEasingCurve.Type.OutCubic, parent=self)
        self._pos_tween.changed.connect(lambda _v: self.update())
        self._hover_tween = motion.ValueTween(0.0, tokens.MOTION["micro"], parent=self)
        self._hover_tween.changed.connect(lambda _v: self.update())
        self._press_tween = motion.ValueTween(0.0, 90, parent=self)
        self._press_tween.changed.connect(lambda _v: self.update())

        self.toggled.connect(self._on_toggled)
        self._update_fixed_metrics()

    def _track_size(self) -> tuple[float, float]:
        return 38.0 * self._scale, 21.0 * self._scale

    def _update_fixed_metrics(self) -> None:
        tw, th = self._track_size()
        h = max(int(round(th + 4 * self._scale)), tokens.spx(26, self._scale))
        if self.text():
            fm = QFontMetrics(self._font)
            w = int(math.ceil(tw + 8.0 * self._scale + fm.horizontalAdvance(self.text()) + 4.0 * self._scale))
            self.setMinimumSize(w, h)
            self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        else:
            w = int(math.ceil(tw + 2.0 * self._scale))
            self.setFixedSize(w, h)

    def setText(self, text: str) -> None:
        super().setText(text)
        self._update_fixed_metrics()

    def setChecked(self, checked: bool) -> None:
        want = bool(checked)
        if want == self.isChecked():
            self._pos_tween.set_immediate(1.0 if want else 0.0)
            return
        super().setChecked(want)

    def _on_toggled(self, checked: bool) -> None:
        self._pos_tween.animate_to(1.0 if checked else 0.0, animate=self.isVisible())
        self.stateChanged.emit(Qt.CheckState.Checked.value if checked else Qt.CheckState.Unchecked.value)

    def enterEvent(self, event):
        self._hover_tween.animate_to(1.0, animate=self.isVisible())
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_tween.animate_to(0.0, animate=self.isVisible())
        self._press_tween.animate_to(0.0, animate=self.isVisible())
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_tween.animate_to(1.0, animate=self.isVisible())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_tween.animate_to(0.0, animate=self.isVisible())
        super().mouseReleaseEvent(event)

    def sizeHint(self) -> QSize:
        tw, th = self._track_size()
        h = max(int(round(th + 4 * self._scale)), tokens.spx(26, self._scale))
        if self.text():
            fm = QFontMetrics(self._font)
            w = int(math.ceil(tw + 8.0 * self._scale + fm.horizontalAdvance(self.text()) + 4.0 * self._scale))
            return QSize(w, h)
        return QSize(int(math.ceil(tw + 2.0 * self._scale)), h)

    def paintEvent(self, event):
        t = tokens.get_tokens(self._dark)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        tw, th = self._track_size()
        ty = (float(self.height()) - th) / 2.0
        tx = 1.0
        pos = self._pos_tween.value
        hv = self._hover_tween.value
        pr = self._press_tween.value

        off_bg = QColor(t.surface_hover if self._dark else t.border_strong)
        if hv > 0.01:
            off_bg = motion.blend_color(off_bg, QColor(t.border_strong if self._dark else t.text_muted), hv * 0.4)
        on_bg = motion.blend_color(QColor(t.accent), QColor(t.accent_hover), hv * 0.65)
        track_col = motion.blend_color(off_bg, on_bg, pos)
        if not self.isEnabled():
            track_col.setAlpha(110)

        track_rect = QRectF(tx, ty, tw, th)
        rad = th / 2.0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track_col)
        p.drawRoundedRect(track_rect, rad, rad)

        rim_c = QColor(255, 255, 255, 34 if self._dark else 90)
        p.setPen(QPen(rim_c, 0.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(track_rect.adjusted(0.5, 0.5, -0.5, -0.5), rad - 0.5, rad - 0.5)

        margin = 2.6 * self._scale
        knob_d = th - margin * 2.0
        stretch = pr * 3.0 * self._scale
        knob_w = knob_d + stretch
        travel = tw - margin * 2.0 - knob_w
        kx = tx + margin + travel * pos
        ky = ty + margin

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 48 if self._dark else 32))
        p.drawRoundedRect(QRectF(kx, ky + 1.0, knob_w, knob_d), knob_d / 2.0, knob_d / 2.0)

        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(QRectF(kx, ky, knob_w, knob_d), knob_d / 2.0, knob_d / 2.0)

        if self.text():
            p.setFont(self._font)
            p.setPen(QColor(t.text if self.isEnabled() else t.text_disabled))
            text_x = tx + tw + 8.0 * self._scale
            p.drawText(QRectF(text_x, 0.0, float(self.width()) - text_x, float(self.height())),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       self.text())
        p.end()


class SlidingSegmentedControl(QWidget):
    """自绘液态滑块分段控制器：胶囊指示器 OutCubic 丝滑跟随 + 悬停微提亮。"""

    currentChanged = Signal(int)

    def __init__(self, items, dark: bool, parent=None, font: QFont | None = None,
                 scale: float = 1.0, height_log: float = 38.0, min_width_log: float | None = None):
        super().__init__(parent)
        self._dark = bool(dark)
        self._items = [str(x) for x in items]
        self._scale = max(1.0, float(scale))
        self._index = 0
        self._hover_idx = -1

        self._font = QFont(font) if font is not None else theme.ui_font(12.5 * self._scale, 500)
        self._font.setFamilies(list(tokens.FONT_TEXT))
        self._font.setPixelSize(tokens.spx(12.0 if height_log <= 34.0 else 12.5, self._scale))
        self._font_active = QFont(self._font)
        self._font_active.setWeight(QFont.Weight.DemiBold)

        self._pill_pos = motion.ValueTween(0.0, tokens.MOTION["standard"],
                                           QEasingCurve.Type.OutCubic, parent=self)
        self._pill_pos.changed.connect(lambda _v: self.update())

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(max(28, tokens.spx(height_log, self._scale)))
        min_w_base = float(min_width_log) if min_width_log is not None else float(max(420, len(self._items) * 82))
        self.setMinimumWidth(max(160, tokens.spx(min_w_base, self._scale)))
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed if min_width_log is not None else QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

    def count(self) -> int:
        return len(self._items)

    def currentIndex(self) -> int:
        return self._index

    def setCurrentIndex(self, idx: int, notify: bool = False) -> None:
        if not self._items:
            return
        idx = max(0, min(int(idx), len(self._items) - 1))
        changed = (idx != self._index)
        self._index = idx
        self._pill_pos.animate_to(float(idx), animate=self.isVisible())
        self.update()
        if notify and changed:
            self.currentChanged.emit(idx)

    def _slot_width(self) -> float:
        pad = 3.0 * self._scale
        return max(1.0, (float(self.width()) - pad * 2.0) / max(1, len(self._items)))

    def _idx_at(self, x: float) -> int:
        pad = 3.0 * self._scale
        sw = self._slot_width()
        idx = int((x - pad) // sw)
        return max(0, min(len(self._items) - 1, idx))

    def mouseMoveEvent(self, event):
        idx = self._idx_at(event.position().x())
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hover_idx != -1:
            self._hover_idx = -1
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._items:
            idx = self._idx_at(event.position().x())
            if idx != self._index:
                self.setCurrentIndex(idx, notify=True)
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left and self._index > 0:
            self.setCurrentIndex(self._index - 1, notify=True)
            return
        if event.key() == Qt.Key.Key_Right and self._index < len(self._items) - 1:
            self.setCurrentIndex(self._index + 1, notify=True)
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        if not self._items:
            return
        t = tokens.get_tokens(self._dark)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        w, h = float(self.width()), float(self.height())
        outer_r = float(tokens.spx(10, self._scale, lo=6))
        pad = 3.0 * self._scale
        inner_r = max(4.0, outer_r - pad * 0.7)

        track_rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        p.setPen(QPen(QColor(t.border), 1.0))
        p.setBrush(QColor(t.surface_sunken))
        p.drawRoundedRect(track_rect, outer_r, outer_r)

        sw = self._slot_width()
        inner_h = h - pad * 2.0

        if 0 <= self._hover_idx < len(self._items) and self._hover_idx != self._index:
            hx = pad + self._hover_idx * sw + 1.0
            hover_rect = QRectF(hx, pad + 1.0, sw - 2.0, inner_h - 2.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 14) if self._dark else QColor(15, 23, 42, 10))
            p.drawRoundedRect(hover_rect, inner_r, inner_r)

        pill_x = pad + self._pill_pos.value * sw
        pill_rect = QRectF(pill_x, pad, sw, inner_h)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 48 if self._dark else 20))
        p.drawRoundedRect(pill_rect.adjusted(0.5, 1.2, -0.5, 0.4), inner_r, inner_r)

        pill_grad = QLinearGradient(0.0, pill_rect.top(), 0.0, pill_rect.bottom())
        if self._dark:
            pill_grad.setColorAt(0.0, QColor("#2A303D"))
            pill_grad.setColorAt(1.0, QColor("#222733"))
        else:
            pill_grad.setColorAt(0.0, QColor("#FFFFFF"))
            pill_grad.setColorAt(1.0, QColor("#FAFBFD"))
        p.setPen(QPen(QColor(t.border_strong if self._dark else t.border), 1.0))
        p.setBrush(pill_grad)
        p.drawRoundedRect(pill_rect.adjusted(0.5, 0.5, -0.5, -0.5), inner_r, inner_r)

        rim = QColor(255, 255, 255, 42 if self._dark else 220)
        p.setPen(QPen(rim, 0.9))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(pill_rect.adjusted(1.2, 1.2, -1.2, -1.2), max(3.0, inner_r - 0.8), max(3.0, inner_r - 0.8))

        pos = self._pill_pos.value
        for i, label in enumerate(self._items):
            cell = QRectF(pad + i * sw, 0.0, sw, h)
            prox = max(0.0, 1.0 - abs(pos - float(i)))
            if i == self._hover_idx and prox < 0.5:
                col = motion.blend_color(QColor(t.text_muted), QColor(t.text), 0.55)
            else:
                col = motion.blend_color(QColor(t.text_muted), QColor(t.text), prox)
            p.setFont(self._font_active if prox > 0.5 else self._font)
            p.setPen(col)
            p.drawText(cell, Qt.AlignmentFlag.AlignCenter, label)
        p.end()


SegmentedControl = SlidingSegmentedControl


class AnimatedIconButton(QPushButton):
    """通用微动效矢量图标按钮（用于删除/编辑等行操作，悬停丝滑渐变 + 按压微缩）。"""

    def __init__(self, icon_name: str, tone: str = "accent",
                 dark: bool = False, scale: float = 1.0,
                 tooltip: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._tone = tone
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if tooltip:
            self.setToolTip(tooltip)

        self._hover_tween = motion.ValueTween(0.0, tokens.MOTION["micro"], parent=self)
        self._hover_tween.changed.connect(lambda _v: self.update())
        self._press_tween = motion.ValueTween(0.0, 80, parent=self)
        self._press_tween.changed.connect(lambda _v: self.update())

    def set_dark_scale(self, dark: bool, scale: float) -> None:
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self.update()

    def enterEvent(self, event):
        self._hover_tween.animate_to(1.0, animate=self.isVisible())
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_tween.animate_to(0.0, animate=self.isVisible())
        self._press_tween.animate_to(0.0, animate=self.isVisible())
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_tween.animate_to(1.0, animate=self.isVisible())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_tween.animate_to(0.0, animate=self.isVisible())
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        t = tokens.get_tokens(self._dark)
        hv = self._hover_tween.value
        pr = self._press_tween.value

        if self._tone == "danger":
            active_fg = QColor(t.danger)
        elif self._tone == "accent":
            active_fg = QColor(t.accent)
        else:
            active_fg = QColor(t.text)

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = float(self.width()), float(self.height())
        rad = float(tokens.spx(7, self._scale, lo=4))

        if hv > 0.005 or pr > 0.005:
            bg_c = QColor(active_fg)
            alpha_base = 28 if self._dark else 20
            bg_c.setAlpha(int(round(alpha_base * hv + 18 * pr)))
            bd_c = QColor(active_fg)
            bd_c.setAlpha(int(round(56 * hv + 36 * pr)))
            p.setBrush(bg_c)
            p.setPen(QPen(bd_c, 1.0))
            p.drawRoundedRect(QRectF(1.0, 1.0, max(2.0, w - 2.0), max(2.0, h - 2.0)), rad, rad)

        ic_color = motion.blend_color(QColor(t.icon_muted), active_fg, max(hv, pr))
        ic_side = min(w, h) * 0.56 * (1.0 - 0.06 * pr)
        ic_rect = QRectF((w - ic_side) / 2.0, (h - ic_side) / 2.0 + 0.6 * pr, ic_side, ic_side)
        icons.paint_icon(p, ic_rect, self._icon_name, ic_color, pen_w=1.55)
        p.end()


class TrashButton(AnimatedIconButton):
    def __init__(self, dark: bool = False, scale: float = 1.0, parent=None):
        super().__init__("trash", tone="danger", dark=dark, scale=scale,
                         tooltip="删除此项", parent=parent)
        self.setObjectName("trashActionBtn")


class EditButton(AnimatedIconButton):
    def __init__(self, dark: bool = False, scale: float = 1.0, parent=None):
        super().__init__("edit", tone="accent", dark=dark, scale=scale,
                         tooltip="编辑详细配置与测试连接", parent=parent)
        self.setObjectName("editActionBtn")
