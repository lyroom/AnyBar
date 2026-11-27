"""app/gui/hover_panel/primitives.py — 悬停浮窗专用视觉原语（全面消除内联 QSS 字符串）"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPalette, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from app.gui import widgets as ui_parts
from app.gui.widgets import motion
from app.styles import icons, qss_engine, theme, tokens

SmoothProgressBar = ui_parts.AnimatedProgressBar
ProbeCircularGauge = ui_parts.AnimatedCircularGauge


def ui_font(px: float, weight: int = 400, mono: bool = False) -> QFont:
    return theme.ui_font(px, weight=weight, mono=mono)


def palette(dark: bool) -> dict:
    """兼容调色板映射：全部字段均由统一 tokens 派生。"""
    t = tokens.get_tokens(dark)
    return {
        "canvas": t.canvas,
        "canvas_border": t.canvas_border_hex,
        "card": t.surface,
        "border": t.border,
        "sep": t.divider,
        "text": t.text,
        "sub": t.text_secondary,
        "dim": t.text_muted,
        "chip_bg": t.surface_elevated,
        "chip_fg": t.text_secondary,
        "green_bg": t.ok_soft,
        "green_fg": t.ok,
        "blue_bg": t.accent_soft,
        "blue_fg": t.accent,
        "violet_bg": t.violet_soft,
        "violet_fg": t.violet,
        "amber": t.warn,
        "track": t.track,
        "input_bg": t.surface_sunken,
        "input_border": t.border,
        "hover": t.surface_hover,
        "done": t.text_muted,
        "done_time": t.text_disabled,
        "accent": t.accent,
    }


def apply_label_color(lbl: QLabel, color: str, role: str | None = None) -> None:
    """使用语义 role 属性与 QPalette 设置标签颜色，消除内联 setStyleSheet 拼接。"""
    if role:
        qss_engine.set_role(lbl, role)
    elif lbl.property("role") is not None:
        qss_engine.set_prop(lbl, "role", None)
    pal = lbl.palette()
    pal.setColor(QPalette.ColorRole.WindowText, QColor(color))
    lbl.setPalette(pal)


def make_label(
    text: str,
    px: float,
    color: str,
    weight: int = 400,
    wrap: bool = False,
    mono: bool = False,
    role: str | None = None,
) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(ui_font(px, weight, mono))
    lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    apply_label_color(lbl, color, role=role)
    if wrap:
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    return lbl


def make_transparent_widget(parent: QWidget | None = None) -> QWidget:
    w = QWidget(parent)
    qss_engine.set_transparent(w, True)
    return w


def make_ghost_link(text: str, scale: float, weight: int = 600, hover_tone: str = "accent",
                    px: float = 11.0) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("ghostLink")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFont(ui_font(px * scale, weight))
    btn.setFlat(True)
    qss_engine.set_prop(btn, "hoverTone", hover_tone, polish=False)
    return btn


def make_card_header(
    icon_name: str,
    icon_color: str,
    title: str,
    right_widget: QWidget | None,
    dark: bool,
    scale: float,
) -> QWidget:
    t = tokens.get_tokens(dark)
    head = make_transparent_widget()
    h = QHBoxLayout(head)
    h.setContentsMargins(tokens.spx(2, scale), 0, tokens.spx(2, scale), 0)
    h.setSpacing(tokens.spx(7, scale))
    h.addWidget(icons.IconWidget(icon_name, icon_color, size=tokens.spx(15, scale)), 0, Qt.AlignmentFlag.AlignVCenter)
    h.addWidget(make_label(title, 13 * scale, t.text, 700, role="primary"), 0, Qt.AlignmentFlag.AlignVCenter)
    h.addStretch(1)
    if right_widget is not None:
        h.addWidget(right_widget, 0, Qt.AlignmentFlag.AlignVCenter)
    return head


class TierCard(ui_parts.SurfaceCard):
    """一级卡片容器：12px 同心圆角 + 液态高光镜面。"""

    def __init__(self, dark: bool, scale: float, radius: float = tokens.RADIUS["card"],
                 parent: QWidget | None = None):
        super().__init__(dark=dark, scale=scale, radius=radius, elevated=False, interactive=False, parent=parent)


class InnerTile(ui_parts.SurfaceCard):
    """二级嵌套子块：8px 同心圆角 + 悬浮可选微提亮。"""

    def __init__(self, dark: bool, scale: float, interactive: bool = False,
                 accent_hover: bool = False, parent: QWidget | None = None):
        super().__init__(dark=dark, scale=scale, radius=tokens.RADIUS["inner"],
                         elevated=True, interactive=interactive, parent=parent)
        if interactive and accent_hover:
            self.set_interactive(True, accent_hover=True)


class Badge(QLabel):
    """高 22 的圆角语义胶囊徽章（由 hover_panel.qss 的 #statusBadge[tone] 驱动）。"""

    def __init__(self, text: str, fg: str = "", bg: str = "", scale: float = 1.0,
                 radius: float = tokens.RADIUS["badge"], weight: int = 600,
                 tone: str | None = None, parent: QWidget | None = None):
        super().__init__(text, parent)
        self._scale = scale
        self._weight = weight
        self._radius = radius
        self.setObjectName("statusBadge")
        self.setFixedHeight(max(18, tokens.spx(22, scale)))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setFont(ui_font(max(9, 10.5 * self._scale), self._weight))
        resolved_tone = tone or self._infer_tone(fg)
        self.set_tone(resolved_tone, fg=fg)

    @staticmethod
    def _infer_tone(fg: str) -> str:
        low = str(fg or "").lower()
        for dark in (True, False):
            t = tokens.get_tokens(dark)
            if low == t.ok.lower():
                return "ok"
            if low == t.warn.lower():
                return "warn"
            if low == t.danger.lower():
                return "danger"
            if low == t.accent.lower():
                return "accent"
            if low == t.info.lower():
                return "info"
            if low == t.violet.lower():
                return "violet"
        return "neutral"

    def set_tone(self, tone: str, fg: str = "") -> None:
        qss_engine.set_prop(self, "tone", tone)
        if fg:
            pal = self.palette()
            pal.setColor(QPalette.ColorRole.WindowText, QColor(fg))
            self.setPalette(pal)

    def restyle(self, fg: str, bg: str = "", tone: str | None = None) -> None:
        self.set_tone(tone or self._infer_tone(fg), fg=fg)


class Divider(QFrame):
    """1px 细分割线（由 common.qss 的 QFrame[role='divider'] 着色）。"""

    def __init__(self, dark: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        qss_engine.set_role(self, "divider", polish=False)


class FrostedGlassTile(QFrame):
    """天气卡内部嵌套子卡：随深浅色主题自适应与其余工具卡同源的磨砂玻璃表面。"""

    clicked = Signal()

    def __init__(self, scale: float, interactive: bool = False,
                 radius: float = tokens.RADIUS["inner"],
                 parent: QWidget | None = None, dark: bool = True):
        super().__init__(parent)
        self._scale = max(1.0, float(scale))
        self._dark = bool(dark)
        self._radius_log = float(radius)
        self._interactive = bool(interactive)
        self._cursor_pos: QPointF | None = None
        self._hover_tween = motion.ValueTween(0.0, tokens.MOTION["fast"], parent=self)
        self._hover_tween.changed.connect(lambda _v: self.update())
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setMouseTracking(True)
        if self._interactive:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, event):
        self._hover_tween.animate_to(1.0, animate=self.isVisible())
        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        self._cursor_pos = event.position()
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_tween.animate_to(0.0, animate=self.isVisible())
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self._interactive and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        t = tokens.get_tokens(self._dark)
        rad = float(tokens.spx(self._radius_log, self._scale, lo=5))
        hv = self._hover_tween.value
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        g = QLinearGradient(0.0, r.top(), 0.0, r.bottom())
        if self._dark:
            g.setColorAt(0.0, QColor(255, 255, 255, int(20 + 16 * hv)))
            g.setColorAt(1.0, QColor(255, 255, 255, int(12 + 12 * hv)))
            bd_c = QColor(255, 255, 255, int(30 + 36 * hv))
        else:
            g.setColorAt(0.0, motion.blend_color(QColor(255, 255, 255, 232), QColor("#F4F8FF"), hv * 0.7))
            g.setColorAt(1.0, motion.blend_color(QColor(247, 250, 254, 224), QColor("#EFF5FF"), hv * 0.6))
            bd_c = motion.blend_color(
                QColor(t.border), QColor(t.accent if self._interactive else t.border_strong), hv * 0.75
            )

        p.setPen(QPen(bd_c, 1.0))
        p.setBrush(g)
        p.drawRoundedRect(r, rad, rad)

        if hv > 0.02 and self._cursor_pos is not None:
            spot_r = max(r.width() * 0.42, 76.0 * self._scale)
            spot = QRadialGradient(self._cursor_pos, spot_r)
            if self._dark:
                spot.setColorAt(0.0, QColor(255, 255, 255, int(34 * hv)))
                spot.setColorAt(1.0, QColor(255, 255, 255, 0))
            else:
                spot.setColorAt(0.0, QColor(37, 99, 235, int(16 * hv)))
                spot.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(spot)
            p.drawRoundedRect(r.adjusted(0.8, 0.8, -0.8, -0.8), max(3.0, rad - 0.8), max(3.0, rad - 0.8))

        rim = QLinearGradient(0.0, r.top(), 0.0, r.bottom())
        rim.setColorAt(0.0, QColor(255, 255, 255, int((52 + 24 * hv) if self._dark else 235)))
        rim.setColorAt(0.45, QColor(255, 255, 255, 14 if self._dark else 110))
        rim.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(rim, 0.9))
        p.drawRoundedRect(r.adjusted(1.0, 1.0, -1.0, -1.0), max(3.0, rad - 1.0), max(3.0, rad - 1.0))
        p.end()


class HoverPill(QWidget):
    """24 小时预报单列 / 7 天预报单行交互底晕胶囊。"""

    def __init__(self, scale: float, active: bool = False, radius: float = 7.0,
                 parent: QWidget | None = None, dark: bool = True):
        super().__init__(parent)
        self._scale = max(1.0, float(scale))
        self._active = bool(active)
        self._dark = bool(dark)
        self._radius_log = float(radius)
        self._hover_tween = motion.ValueTween(0.0, tokens.MOTION["micro"], parent=self)
        self._hover_tween.changed.connect(lambda _v: self.update())

    def enterEvent(self, event):
        self._hover_tween.animate_to(1.0, animate=self.isVisible())
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_tween.animate_to(0.0, animate=self.isVisible())
        super().leaveEvent(event)

    def paintEvent(self, event):
        hv = self._hover_tween.value
        if not self._active and hv <= 0.005:
            return
        rad = float(tokens.spx(self._radius_log, self._scale, lo=4))
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._dark:
            alpha_bg = int((42 if self._active else 0) + (28 if not self._active else 18) * hv)
            alpha_bd = int((62 if self._active else 0) + 40 * hv)
            p.setBrush(QColor(255, 255, 255, min(255, alpha_bg)))
            p.setPen(QPen(QColor(255, 255, 255, min(255, alpha_bd)), 0.85) if alpha_bd > 8 else Qt.PenStyle.NoPen)
        else:
            if self._active:
                p.setBrush(QColor(37, 99, 235, int(20 + 12 * hv)))
                p.setPen(QPen(QColor(37, 99, 235, int(68 + 32 * hv)), 0.9))
            else:
                p.setBrush(QColor(15, 23, 42, int(14 * hv)))
                p.setPen(QPen(QColor(15, 23, 42, int(22 * hv)), 0.85))
        p.drawRoundedRect(r, rad, rad)
        p.end()


_HoverPill = HoverPill
