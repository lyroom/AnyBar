"""app/gui/widgets/surfaces.py — 光学拟真卡片与设置分组容器"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.styles import icons, qss_engine, theme, tokens

from . import motion


class SurfaceCard(QFrame):
    """iOS 扁平拟真光学卡片：双层柔散投影 + 微凸梯度表面 + 顶缘镜面折射 + 鼠标跟手柔光与按压弹性。"""

    clicked = Signal()

    def __init__(self, dark: bool = True, scale: float = 1.0,
                 radius: float = tokens.RADIUS["card"],
                 elevated: bool = False, interactive: bool = False,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self._radius_log = float(radius)
        self._elevated = bool(elevated)
        self._interactive = bool(interactive)
        self._accent_hover = False
        self._cursor_pos: QPointF | None = None
        self._hover_tween = motion.ValueTween(0.0, tokens.MOTION["fast"], parent=self)
        self._hover_tween.changed.connect(lambda _v: self.update())
        self._press_tween = motion.ValueTween(0.0, 95, parent=self)
        self._press_tween.changed.connect(lambda _v: self.update())
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        if self._interactive:
            self.setMouseTracking(True)
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_interactive(self, interactive: bool, accent_hover: bool = False) -> None:
        self._interactive = bool(interactive)
        self._accent_hover = bool(accent_hover)
        self.setMouseTracking(self._interactive)
        self.setCursor(Qt.CursorShape.PointingHandCursor if interactive
                       else Qt.CursorShape.ArrowCursor)
        self.update()

    def set_dark_scale(self, dark: bool, scale: float) -> None:
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self.update()

    def enterEvent(self, event):
        if self._interactive:
            self._hover_tween.animate_to(1.0, animate=self.isVisible())
        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        if self._interactive:
            self._cursor_pos = event.position()
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._interactive:
            self._hover_tween.animate_to(0.0, animate=self.isVisible())
            self._press_tween.animate_to(0.0, animate=self.isVisible())
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self._interactive and event.button() == Qt.MouseButton.LeftButton:
            self._press_tween.animate_to(1.0, animate=self.isVisible())
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._interactive and event.button() == Qt.MouseButton.LeftButton:
            self._press_tween.animate_to(0.0, animate=self.isVisible())
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        t = tokens.get_tokens(self._dark)
        rad = float(tokens.spx(self._radius_log, self._scale, lo=4))
        hv = self._hover_tween.value if self._interactive else 0.0
        pr = self._press_tween.value if self._interactive else 0.0

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. 双层轻拟物环境柔影（近距接触影 + 柔和漫散影，悬停微抬升）
        lift = hv * 0.7 * self._scale - pr * 0.6 * self._scale
        if not self._elevated:
            far_shadow = QRectF(self.rect()).adjusted(0.6, 2.2 + lift * 0.6, -0.6, 0.2)
            p.setPen(Qt.PenStyle.NoPen)
            sc_far = QColor(*t.shadow_ambient)
            sc_far.setAlpha(min(255, int(sc_far.alpha() * (0.75 + 0.45 * hv))))
            p.setBrush(sc_far)
            p.drawRoundedRect(far_shadow, rad, rad)

            near_shadow = QRectF(self.rect()).adjusted(0.8, 1.1, -0.8, -0.2)
            sc_near = QColor(0, 0, 0, 26 if self._dark else 13)
            p.setBrush(sc_near)
            p.drawRoundedRect(near_shadow, rad, rad)
        elif hv > 0.02:
            sub_shadow = QRectF(self.rect()).adjusted(0.8, 1.3, -0.8, 0.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, int((28 if self._dark else 14) * hv)))
            p.drawRoundedRect(sub_shadow, rad, rad)

        # 2. 光学软枕微梯度主体（顶部微亮、底部微沉，呈现柔和体积感）
        inset_y = 0.6 + pr * 0.4
        r = QRectF(self.rect()).adjusted(0.6, inset_y, -0.6, -1.4 if not self._elevated else -0.7)
        if self._elevated:
            base_top = QColor("#292E3B" if self._dark else "#FFFFFF")
            base_bot = QColor(t.surface_elevated if self._dark else "#F2F6FC")
        else:
            base_top = QColor(t.surface_top)
            base_bot = QColor(t.surface if self._dark else "#F9FBFE")
        if hv > 0.005:
            hover_c = QColor("#303747" if self._dark else "#F4F8FF")
            base_top = motion.blend_color(base_top, hover_c, hv * 0.78)
            base_bot = motion.blend_color(base_bot, hover_c, hv * 0.55)
        body_grad = QLinearGradient(0.0, r.top(), 0.0, r.bottom())
        body_grad.setColorAt(0.0, base_top)
        body_grad.setColorAt(1.0, base_bot)

        bd_col = QColor(t.border)
        if hv > 0.005:
            target_bd = QColor(t.accent if self._accent_hover else t.border_strong)
            if self._accent_hover:
                target_bd.setAlpha(175)
            bd_col = motion.blend_color(bd_col, target_bd, hv)
        p.setPen(QPen(bd_col, 1.0))
        p.setBrush(body_grad)
        p.drawRoundedRect(r, rad, rad)

        # 3. 鼠标跟手镜面光泽（Liquid Glass pointer specular）
        if hv > 0.02 and self._cursor_pos is not None:
            spot_r = max(r.width() * 0.45, 90.0 * self._scale)
            spot = QRadialGradient(self._cursor_pos, spot_r)
            if self._dark:
                spot.setColorAt(0.0, QColor(255, 255, 255, int(30 * hv)))
                spot.setColorAt(0.55, QColor(92, 164, 255, int(12 * hv)))
                spot.setColorAt(1.0, QColor(255, 255, 255, 0))
            else:
                spot.setColorAt(0.0, QColor(255, 255, 255, int(190 * hv)))
                spot.setColorAt(0.55, QColor(37, 99, 235, int(12 * hv)))
                spot.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(spot)
            p.drawRoundedRect(r.adjusted(0.8, 0.8, -0.8, -0.8), max(2.0, rad - 0.8), max(2.0, rad - 0.8))

        # 4. 顶缘镜面高光折射描边
        inner_r = r.adjusted(0.8, 0.8, -0.8, -0.8)
        rim_grad = QLinearGradient(0.0, inner_r.top(), 0.0, inner_r.bottom())
        rim_grad.setColorAt(0.0, QColor(*t.rim_top))
        rim_grad.setColorAt(0.45, QColor(*t.rim_mid))
        rim_grad.setColorAt(1.0, QColor(*t.rim_bottom))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(rim_grad, 1.0))
        in_rad = max(2.0, rad - 0.8)
        p.drawRoundedRect(inner_r, in_rad, in_rad)
        p.end()


class SettingGroupCard(SurfaceCard):
    """设置页分组卡片：可选分组头 + 自动插入 1px 内缩细分割线，样式由外部 QSS 规则驱动。"""

    def __init__(self, dark: bool = True, scale: float = 1.0,
                 title: str = "", icon_name: str = "",
                 header_right: QWidget | None = None,
                 parent: QWidget | None = None):
        super().__init__(dark=dark, scale=scale, radius=tokens.RADIUS["card"],
                         elevated=False, interactive=False, parent=parent)
        self._rows_count = 0
        self._v = QVBoxLayout(self)
        pad_x = tokens.spx(14, scale)
        pad_y = tokens.spx(8, scale)
        self._v.setContentsMargins(pad_x, pad_y, pad_x, pad_y)
        self._v.setSpacing(0)

        if title:
            t = tokens.get_tokens(dark)
            hdr = QWidget()
            hdr.setObjectName("groupHeader")
            hh = QHBoxLayout(hdr)
            hh.setContentsMargins(0, tokens.spx(2, scale), 0, tokens.spx(8, scale))
            hh.setSpacing(tokens.spx(8, scale))
            if icon_name:
                hh.addWidget(icons.IconWidget(icon_name, t.accent,
                                              size=tokens.spx(15, scale)),
                             0, Qt.AlignmentFlag.AlignVCenter)
            lbl = QLabel(title)
            lbl.setObjectName("sectionTitle")
            lbl.setFont(theme.ui_font(13 * scale, 600))
            hh.addWidget(lbl, 0, Qt.AlignmentFlag.AlignVCenter)
            hh.addStretch(1)
            if header_right is not None:
                hh.addWidget(header_right, 0, Qt.AlignmentFlag.AlignVCenter)
            self._v.addWidget(hdr)
            self._add_divider()

    def _add_divider(self) -> None:
        div = QFrame()
        div.setFixedHeight(1)
        qss_engine.set_role(div, "divider", polish=False)
        self._v.addWidget(div)

    def add_row(self, widget: QWidget, divider: bool = True) -> None:
        if self._rows_count > 0 and divider:
            self._add_divider()
        self._v.addWidget(widget)
        self._rows_count += 1

    def add_setting_row(self, label_text: str, controls: list[QWidget],
                        desc: str = "", min_height: int = 40) -> QWidget:
        row = QWidget()
        row.setObjectName("settingRow")
        row.setMinimumHeight(tokens.spx(min_height, self._scale))
        h = QHBoxLayout(row)
        h.setContentsMargins(0, tokens.spx(6, self._scale), 0, tokens.spx(6, self._scale))
        h.setSpacing(tokens.spx(10, self._scale))

        if desc:
            lv = QVBoxLayout()
            lv.setContentsMargins(0, 0, 0, 0)
            lv.setSpacing(tokens.spx(2, self._scale))
            lbl = QLabel(label_text)
            lbl.setFont(theme.ui_font(12.5 * self._scale, 500))
            lv.addWidget(lbl)
            dl = QLabel(desc)
            dl.setObjectName("mutedTip")
            qss_engine.set_role(dl, "muted", polish=False)
            dl.setWordWrap(True)
            dl.setFont(theme.ui_font(11 * self._scale, 400))
            lv.addWidget(dl)
            h.addLayout(lv, 1)
        else:
            lbl = QLabel(label_text)
            lbl.setFont(theme.ui_font(12.5 * self._scale, 500))
            h.addWidget(lbl)
            h.addStretch(1)

        for ctrl in controls:
            h.addWidget(ctrl, 0, Qt.AlignmentFlag.AlignVCenter)
        self.add_row(row)
        return row
