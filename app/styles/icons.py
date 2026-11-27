"""app/icons.py — AnyBar 统一矢量图标库（1.5px 圆头线性矢量，替代零散 Emoji）

全部图标基于 16×16 逻辑坐标系绘制，在 100%~200% 任意 DPI 下保持锐利一致的视觉笔触。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from . import tokens


# ── 基础 16×16 矢量画笔函数（逻辑坐标 0..16） ─────────────────────────────

def _ic_pause(p: QPainter):
    p.drawLine(QPointF(5.5, 4.0), QPointF(5.5, 12.0))
    p.drawLine(QPointF(10.5, 4.0), QPointF(10.5, 12.0))


def _ic_play(p: QPainter):
    p.setBrush(p.pen().color())
    p.drawPolygon([QPointF(5.2, 3.8), QPointF(12.2, 8.0), QPointF(5.2, 12.2)])


def _ic_focus(p: QPainter):
    c = QPointF(8.0, 8.0)
    p.drawEllipse(c, 5.4, 5.4)
    p.drawEllipse(c, 1.3, 1.3)
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        p.drawLine(QPointF(c.x() + dx * 3.4, c.y() + dy * 3.4),
                   QPointF(c.x() + dx * 5.4, c.y() + dy * 5.4))


def _ic_todo(p: QPainter):
    p.drawLine(QPointF(2.2, 4.2), QPointF(3.8, 5.8))
    p.drawLine(QPointF(3.8, 5.8), QPointF(6.4, 2.8))
    p.drawLine(QPointF(8.2, 4.5), QPointF(13.8, 4.5))
    p.drawLine(QPointF(2.2, 8.6), QPointF(3.8, 10.2))
    p.drawLine(QPointF(3.8, 10.2), QPointF(6.4, 7.2))
    p.drawLine(QPointF(8.2, 8.9), QPointF(13.8, 8.9))
    p.drawLine(QPointF(8.2, 13.0), QPointF(13.8, 13.0))
    p.drawEllipse(QPointF(4.0, 13.0), 1.0, 1.0)


def _ic_launch(p: QPainter):
    p.drawPolyline([
        QPointF(3.0, 13.2), QPointF(12.8, 2.8),
        QPointF(11.6, 11.4), QPointF(7.6, 9.2),
        QPointF(5.4, 12.2), QPointF(3.0, 13.2),
    ])


def _ic_refresh(p: QPainter):
    p.drawArc(QRectF(3.0, 3.0, 10.0, 10.0), 35 * 16, 290 * 16)
    ex = 8.0 + 5.0 * math.cos(math.radians(35))
    ey = 8.0 - 5.0 * math.sin(math.radians(35))
    p.drawLine(QPointF(ex, ey), QPointF(ex + 0.4, ey - 2.3))
    p.drawLine(QPointF(ex, ey), QPointF(ex - 2.2, ey + 0.2))


def _ic_reset(p: QPainter):
    p.drawArc(QRectF(2.8, 2.8, 10.4, 10.4), 140 * 16, -285 * 16)
    ex = 8.0 + 5.2 * math.cos(math.radians(140))
    ey = 8.0 - 5.2 * math.sin(math.radians(140))
    p.drawLine(QPointF(ex, ey), QPointF(ex - 1.4, ey - 2.3))
    p.drawLine(QPointF(ex, ey), QPointF(ex - 2.5, ey + 0.1))


def _ic_settings(p: QPainter):
    c = QPointF(8.0, 8.0)
    p.drawEllipse(c, 2.4, 2.4)
    for k in range(8):
        a = math.radians(k * 45)
        p.drawLine(QPointF(c.x() + 3.8 * math.cos(a), c.y() + 3.8 * math.sin(a)),
                   QPointF(c.x() + 5.6 * math.cos(a), c.y() + 5.6 * math.sin(a)))


def _ic_quit(p: QPainter):
    p.drawLine(QPointF(4.2, 4.2), QPointF(11.8, 11.8))
    p.drawLine(QPointF(11.8, 4.2), QPointF(4.2, 11.8))


def _ic_music(p: QPainter):
    p.drawLine(QPointF(7.2, 3.0), QPointF(7.2, 11.4))
    p.drawEllipse(QPointF(5.4, 11.8), 1.9, 1.5)
    p.drawLine(QPointF(7.2, 3.0), QPointF(12.2, 4.5))
    p.drawLine(QPointF(7.2, 5.8), QPointF(12.2, 7.3))


def _ic_switch(p: QPainter):
    p.drawEllipse(QPointF(8.0, 8.0), 5.2, 5.2)
    p.drawEllipse(QPointF(8.0, 8.0), 2.1, 2.1)


def _ic_trash(p: QPainter):
    p.drawLine(QPointF(5.8, 2.6), QPointF(10.2, 2.6))
    p.drawLine(QPointF(2.8, 4.4), QPointF(13.2, 4.4))
    p.drawRoundedRect(QRectF(4.0, 4.4, 8.0, 9.2), 1.6, 1.6)
    p.drawLine(QPointF(6.6, 7.0), QPointF(6.6, 11.2))
    p.drawLine(QPointF(9.4, 7.0), QPointF(9.4, 11.2))


def _ic_edit(p: QPainter):
    p.save()
    p.translate(8.0, 7.6)
    p.rotate(-45)
    p.drawPolyline([
        QPointF(-2.2, -1.7), QPointF(4.4, -1.7), QPointF(4.4, 1.7),
        QPointF(-2.2, 1.7), QPointF(-5.0, 0.0), QPointF(-2.2, -1.7),
    ])
    p.drawLine(QPointF(-2.2, -1.7), QPointF(-2.2, 1.7))
    p.drawLine(QPointF(2.5, -1.7), QPointF(2.5, 1.7))
    p.restore()
    p.drawLine(QPointF(2.6, 13.4), QPointF(13.4, 13.4))


def _ic_capsule(p: QPainter):
    p.drawRoundedRect(QRectF(2.6, 4.0, 4.6, 8.0), 2.2, 2.2)
    p.drawRoundedRect(QRectF(8.8, 4.0, 4.6, 8.0), 2.2, 2.2)


def _ic_check(p: QPainter):
    p.drawPolyline([QPointF(3.2, 8.2), QPointF(6.5, 11.5), QPointF(12.8, 4.6)])


def _ic_empty(p: QPainter):
    pass


def _ic_rotate(p: QPainter):
    p.drawArc(QRectF(3.0, 3.0, 10.0, 10.0), 30 * 16, 120 * 16)
    p.drawLine(QPointF(11.4, 4.6), QPointF(13.2, 4.0))
    p.drawLine(QPointF(11.4, 4.6), QPointF(11.6, 6.4))
    p.drawArc(QRectF(3.0, 3.0, 10.0, 10.0), 210 * 16, 120 * 16)
    p.drawLine(QPointF(4.6, 11.4), QPointF(2.8, 12.0))
    p.drawLine(QPointF(4.6, 11.4), QPointF(4.4, 9.6))


def _ic_schedule(p: QPainter):
    p.drawRoundedRect(QRectF(2.4, 3.2, 11.2, 10.4), 2.2, 2.2)
    p.drawLine(QPointF(2.6, 6.6), QPointF(13.4, 6.6))
    p.drawLine(QPointF(5.4, 2.0), QPointF(5.4, 4.4))
    p.drawLine(QPointF(10.6, 2.0), QPointF(10.6, 4.4))
    p.drawLine(QPointF(5.4, 9.6), QPointF(7.8, 9.6))
    p.drawLine(QPointF(5.4, 11.6), QPointF(10.4, 11.6))


def _ic_cpu(p: QPainter):
    p.drawRoundedRect(QRectF(4.2, 4.2, 7.6, 7.6), 1.5, 1.5)
    p.drawRoundedRect(QRectF(6.5, 6.5, 3.0, 3.0), 0.6, 0.6)
    for pos in (6.2, 9.8):
        p.drawLine(QPointF(pos, 2.0), QPointF(pos, 4.0))
        p.drawLine(QPointF(pos, 12.0), QPointF(pos, 14.0))
        p.drawLine(QPointF(2.0, pos), QPointF(4.0, pos))
        p.drawLine(QPointF(12.0, pos), QPointF(14.0, pos))


def _ic_spark(p: QPainter):
    path = QPainterPath()
    path.moveTo(8.0, 1.8)
    path.quadTo(8.3, 7.7, 14.2, 8.0)
    path.quadTo(8.3, 8.3, 8.0, 14.2)
    path.quadTo(7.7, 8.3, 1.8, 8.0)
    path.quadTo(7.7, 7.7, 8.0, 1.8)
    p.drawPath(path)


def _ic_weather(p: QPainter):
    p.drawArc(QRectF(2.6, 2.6, 5.2, 5.2), 20 * 16, 220 * 16)
    p.drawRoundedRect(QRectF(4.4, 7.8, 9.2, 4.8), 2.4, 2.4)
    p.drawArc(QRectF(6.2, 5.2, 5.4, 5.2), 0, 180 * 16)


def _ic_git(p: QPainter):
    p.drawEllipse(QPointF(4.8, 3.8), 1.6, 1.6)
    p.drawEllipse(QPointF(4.8, 12.2), 1.6, 1.6)
    p.drawEllipse(QPointF(11.4, 5.6), 1.6, 1.6)
    p.drawLine(QPointF(4.8, 5.4), QPointF(4.8, 10.6))
    path = QPainterPath()
    path.moveTo(11.4, 7.2)
    path.quadTo(11.4, 10.4, 6.4, 11.4)
    p.drawPath(path)


def _ic_layers(p: QPainter):
    p.drawPolygon([QPointF(8.0, 2.4), QPointF(13.8, 5.6), QPointF(8.0, 8.8), QPointF(2.2, 5.6)])
    p.drawPolyline([QPointF(2.4, 8.8), QPointF(8.0, 11.8), QPointF(13.6, 8.8)])
    p.drawPolyline([QPointF(2.4, 11.6), QPointF(8.0, 14.4), QPointF(13.6, 11.6)])


def _ic_plugin(p: QPainter):
    p.drawRoundedRect(QRectF(3.0, 4.6, 10.0, 8.8), 2.0, 2.0)
    p.drawLine(QPointF(6.0, 2.2), QPointF(6.0, 4.6))
    p.drawLine(QPointF(10.0, 2.2), QPointF(10.0, 4.6))
    p.drawLine(QPointF(6.2, 9.0), QPointF(9.8, 9.0))


def _ic_folder(p: QPainter):
    p.drawPolyline([
        QPointF(2.2, 4.2), QPointF(6.4, 4.2), QPointF(7.8, 5.8),
        QPointF(13.8, 5.8), QPointF(13.8, 12.8), QPointF(2.2, 12.8),
        QPointF(2.2, 4.2),
    ])


def _ic_bolt(p: QPainter):
    p.drawPolygon([
        QPointF(9.2, 2.0), QPointF(4.2, 8.8), QPointF(7.8, 8.8),
        QPointF(6.8, 14.0), QPointF(11.8, 7.2), QPointF(8.2, 7.2),
    ])


def _ic_search(p: QPainter):
    p.drawEllipse(QPointF(7.0, 7.0), 4.4, 4.4)
    p.drawLine(QPointF(10.3, 10.3), QPointF(13.6, 13.6))


def _ic_shield(p: QPainter):
    path = QPainterPath()
    path.moveTo(8.0, 2.0)
    path.lineTo(13.0, 4.0)
    path.lineTo(13.0, 8.2)
    path.quadTo(13.0, 12.2, 8.0, 14.2)
    path.quadTo(3.0, 12.2, 3.0, 8.2)
    path.lineTo(3.0, 4.0)
    path.closeSubpath()
    p.drawPath(path)
    p.drawPolyline([QPointF(5.8, 8.2), QPointF(7.4, 9.8), QPointF(10.4, 6.4)])


def _ic_info(p: QPainter):
    p.drawEllipse(QPointF(8.0, 8.0), 5.6, 5.6)
    p.drawLine(QPointF(8.0, 7.4), QPointF(8.0, 11.2))
    p.drawPoint(QPointF(8.0, 5.0))


def _ic_terminal(p: QPainter):
    p.drawRoundedRect(QRectF(2.2, 3.0, 11.6, 10.0), 2.0, 2.0)
    p.drawPolyline([QPointF(4.6, 6.2), QPointF(6.8, 8.0), QPointF(4.6, 9.8)])
    p.drawLine(QPointF(8.4, 10.0), QPointF(11.4, 10.0))


def _ic_radar(p: QPainter):
    p.drawEllipse(QPointF(8.0, 8.0), 5.4, 5.4)
    p.drawEllipse(QPointF(8.0, 8.0), 2.6, 2.6)
    p.drawLine(QPointF(8.0, 8.0), QPointF(12.2, 4.0))


def _ic_pin(p: QPainter):
    path = QPainterPath()
    path.moveTo(8.0, 14.0)
    path.quadTo(3.4, 9.8, 3.4, 6.4)
    path.arcTo(QRectF(3.4, 1.8, 9.2, 9.2), 180, -180)
    path.quadTo(12.6, 9.8, 8.0, 14.0)
    p.drawPath(path)
    p.drawEllipse(QPointF(8.0, 6.4), 1.6, 1.6)


def _ic_network(p: QPainter):
    p.drawLine(QPointF(5.4, 12.6), QPointF(5.4, 3.6))
    p.drawPolyline([QPointF(3.2, 5.8), QPointF(5.4, 3.6), QPointF(7.6, 5.8)])
    p.drawLine(QPointF(10.6, 3.4), QPointF(10.6, 12.4))
    p.drawPolyline([QPointF(8.4, 10.2), QPointF(10.6, 12.4), QPointF(12.8, 10.2)])


def _ic_plus(p: QPainter):
    p.drawLine(QPointF(8.0, 3.4), QPointF(8.0, 12.6))
    p.drawLine(QPointF(3.4, 8.0), QPointF(12.6, 8.0))


def _ic_chevron_down(p: QPainter):
    p.drawPolyline([QPointF(4.0, 6.0), QPointF(8.0, 10.2), QPointF(12.0, 6.0)])


def _ic_chevron_up(p: QPainter):
    p.drawPolyline([QPointF(4.0, 10.0), QPointF(8.0, 5.8), QPointF(12.0, 10.0)])


def _ic_chevron_right(p: QPainter):
    p.drawPolyline([QPointF(6.0, 4.0), QPointF(10.2, 8.0), QPointF(6.0, 12.0)])


def _ic_sun(p: QPainter):
    c = QPointF(8.0, 8.0)
    p.drawEllipse(c, 3.0, 3.0)
    for k in range(8):
        a = math.radians(k * 45)
        p.drawLine(QPointF(c.x() + 4.8 * math.cos(a), c.y() + 4.8 * math.sin(a)),
                   QPointF(c.x() + 6.2 * math.cos(a), c.y() + 6.2 * math.sin(a)))


def _ic_moon(p: QPainter):
    path = QPainterPath()
    path.moveTo(10.8, 3.2)
    path.cubicTo(6.2, 3.5, 3.6, 7.6, 5.2, 11.2)
    path.cubicTo(6.6, 13.8, 10.6, 14.1, 12.8, 11.4)
    path.cubicTo(9.8, 11.8, 7.8, 9.5, 8.3, 6.4)
    path.cubicTo(8.6, 4.9, 9.6, 3.8, 10.8, 3.2)
    p.drawPath(path)


def _ic_theme(p: QPainter):
    """明暗半圆对比图标（与设置齿轮清晰区分）。"""
    rect = QRectF(2.6, 2.6, 10.8, 10.8)
    p.drawEllipse(rect)
    half = QPainterPath()
    half.moveTo(8.0, 2.6)
    half.arcTo(rect, 90, -180)
    half.closeSubpath()
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(p.pen().color())
    p.drawPath(half)
    p.restore()


ICON_PAINTERS = {
    "switch": _ic_switch,
    "pause": _ic_pause,
    "play": _ic_play,
    "focus": _ic_focus,
    "todo": _ic_todo,
    "launch": _ic_launch,
    "refresh": _ic_refresh,
    "reset": _ic_reset,
    "settings": _ic_settings,
    "quit": _ic_quit,
    "music": _ic_music,
    "trash": _ic_trash,
    "edit": _ic_edit,
    "rotate": _ic_rotate,
    "check": _ic_check,
    "empty": _ic_empty,
    "capsule": _ic_capsule,
    "schedule": _ic_schedule,
    "cpu": _ic_cpu,
    "spark": _ic_spark,
    "weather": _ic_weather,
    "git": _ic_git,
    "layers": _ic_layers,
    "plugin": _ic_plugin,
    "folder": _ic_folder,
    "bolt": _ic_bolt,
    "search": _ic_search,
    "shield": _ic_shield,
    "info": _ic_info,
    "terminal": _ic_terminal,
    "radar": _ic_radar,
    "pin": _ic_pin,
    "network": _ic_network,
    "plus": _ic_plus,
    "chevron_down": _ic_chevron_down,
    "chevron_up": _ic_chevron_up,
    "chevron_right": _ic_chevron_right,
    "sun": _ic_sun,
    "moon": _ic_moon,
    "theme": _ic_theme,
}


def paint_icon(painter: QPainter, rect: QRectF, name: str, color: str | QColor,
               pen_w: float = 1.55) -> None:
    """在指定矩形内居中绘制 16×16 矢量图标。"""
    fn = ICON_PAINTERS.get(name)
    if fn is None:
        return
    side = min(rect.width(), rect.height())
    if side <= 1.0:
        return
    x0 = rect.x() + (rect.width() - side) / 2.0
    y0 = rect.y() + (rect.height() - side) / 2.0
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(x0, y0)
    scale = side / 16.0
    painter.scale(scale, scale)
    pen = QPen(QColor(color), pen_w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    fn(painter)
    painter.restore()


def make_qicon(name: str, color: str | QColor, size: int = 16,
               pen_w: float = 1.55) -> QIcon:
    """生成高分率 2x 渲染的 QIcon。"""
    sz = max(12, int(round(size)))
    pm = QPixmap(sz * 2, sz * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    paint_icon(p, QRectF(0.0, 0.0, float(sz), float(sz)), name, color, pen_w=pen_w)
    p.end()
    return QIcon(pm)


def make_state_qicon(off_name: str, on_name: str, color: str | QColor,
                     size: int = 16, pen_w: float = 1.55) -> QIcon:
    """生成支持 Checkable Action Off/On 自动切换状态的双态 QIcon。"""
    sz = max(12, int(round(size)))
    icon = QIcon()
    for nm, state in ((off_name, QIcon.State.Off), (on_name, QIcon.State.On)):
        pm = QPixmap(sz * 2, sz * 2)
        pm.setDevicePixelRatio(2.0)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        paint_icon(p, QRectF(0.0, 0.0, float(sz), float(sz)), nm, color, pen_w=pen_w)
        p.end()
        icon.addPixmap(pm, QIcon.Mode.Normal, state)
    return icon


def build_menu_icons(dark: bool, size: int = 16) -> dict[str, QIcon]:
    """构建右键菜单全套矢量图标（颜色取自统一 tokens）。"""
    color = tokens.get_tokens(dark).icon
    out = {name: make_qicon(name, color, size=size) for name in ICON_PAINTERS}
    out["capsule"] = make_state_qicon("capsule", "check", color, size=size)
    out["launch"] = make_state_qicon("launch", "check", color, size=size)
    return out


def app_window_icon() -> QIcon:
    """绘制 Liquid Fluent 风格圆角光环应用图标。"""
    icon = QIcon()
    for sz in (32, 64):
        pm = QPixmap(sz, sz)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        s = float(sz)
        rect = QRectF(s * 0.06, s * 0.06, s * 0.88, s * 0.88)
        bg = QLinearGradient(0.0, rect.top(), 0.0, rect.bottom())
        bg.setColorAt(0.0, QColor("#222630"))
        bg.setColorAt(1.0, QColor("#121418"))
        p.setPen(QPen(QColor(255, 255, 255, 48), max(1.0, s * 0.03)))
        p.setBrush(bg)
        p.drawRoundedRect(rect, s * 0.24, s * 0.24)

        r = s * 0.27
        cx, cy = s * 0.5, s * 0.5
        stroke = max(2.2, s * 0.11)
        ring_rect = QRectF(cx - r, cy - r, 2.0 * r, 2.0 * r)
        track_pen = QPen(QColor(255, 255, 255, 42), stroke)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(track_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(ring_rect)

        arc_grad = QLinearGradient(ring_rect.left(), ring_rect.top(),
                                   ring_rect.right(), ring_rect.bottom())
        arc_grad.setColorAt(0.0, QColor("#5CA4FF"))
        arc_grad.setColorAt(1.0, QColor("#34D399"))
        arc_pen = QPen(arc_grad, stroke)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(arc_pen)
        p.drawArc(ring_rect, 90 * 16, -int(275 * 16))
        p.end()
        icon.addPixmap(pm)
    return icon


class IconWidget(QWidget):
    """轻量级矢量图标小部件：支持高 DPI 缩放与动态换色。"""

    def __init__(self, name: str, color: str | QColor, size: int = 16,
                 pen_w: float = 1.55, parent: QWidget | None = None):
        super().__init__(parent)
        self._name = str(name)
        self._color = QColor(color)
        self._pen_w = float(pen_w)
        sz = max(12, int(round(size)))
        self.setFixedSize(sz, sz)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_icon(self, name: str) -> None:
        if name != self._name:
            self._name = str(name)
            self.update()

    def set_color(self, color: str | QColor) -> None:
        c = QColor(color)
        if c != self._color:
            self._color = c
            self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        paint_icon(p, QRectF(self.rect()), self._name, self._color, pen_w=self._pen_w)
        p.end()
