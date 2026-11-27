"""app/gui/taskbar/views/schedule_view.py — 日程提醒 + 待办跑马灯 + 专注倒计时视图策略"""

from __future__ import annotations

import datetime
import math
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

from app.core import config as config_mod
from app.styles import theme, tokens

from . import BarViewStrategy, VIEW_LABELS, VIEW_SCHEDULE
from .shared_painters import optical_line_height, preferred_families, schedule_ring_geometry

if TYPE_CHECKING:
    from app.gui.taskbar.widget import BarWidget


def paint_scrolling_row2(bar: BarWidget, painter: QPainter, content_rect: QRect, color: QColor | None = None) -> None:
    """绘制带离屏边缘渐隐羽化的循环滚动跑马灯下行文本。"""
    w = content_rect.width()
    h = content_rect.height()
    if w <= 2 or h <= 2:
        return
    key = (w, h)
    if bar._row2_pm is None or bar._row2_pm_key != key:
        bar._row2_pm = QPixmap(w, h)
        bar._row2_pm_key = key
    pm = bar._row2_pm
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setFont(bar._font_row2)
    p.setPen(color if color is not None else bar._row2_color)
    fm = bar._fm()
    y = int((h + fm.ascent() - fm.descent()) / 2)
    loop = bar._text_width(bar._row2) + bar._gap
    x = -bar._offset
    p.drawText(int(x), y, bar._row2)
    p.drawText(int(x + loop), y, bar._row2)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    fade = bar._fade_px
    if fade * 2 < w:
        grad = QLinearGradient(0, 0, w, 0)
        transparent = QColor(0, 0, 0, 0)
        opaque = QColor(0, 0, 0, 255)
        if bar._offset > 1.0:
            grad.setColorAt(0.0, transparent)
            grad.setColorAt(min(0.45, fade / w), opaque)
        else:
            grad.setColorAt(0.0, opaque)
        grad.setColorAt(max(0.55, 1.0 - fade / w), opaque)
        grad.setColorAt(1.0, transparent)
        p.fillRect(QRect(0, 0, w, h), grad)
    p.end()
    painter.drawPixmap(content_rect.x(), content_rect.y(), pm)


def paint_focus_ring(bar: BarWidget, painter: QPainter, rect: QRect, hig: dict) -> None:
    side = min(rect.width(), rect.height())
    d = max(8.0, side * 0.8)
    cx = rect.center().x()
    cy = rect.center().y()
    stroke = max(1.6, 2.2 * bar._scale)
    m = stroke / 2.0 + 0.5
    ring_rect = QRectF(cx - d / 2.0 + m, cy - d / 2.0 + m, d - 2 * m, d - 2 * m)
    track = QColor(hig["bar_row2"])
    track.setAlpha(40)
    pen = QPen(track, stroke)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(pen)
    painter.drawEllipse(ring_rect)
    total = max(1.0, float(bar._focus_total))
    remain = max(0.0, bar._focus_until - time.monotonic())
    frac = min(1.0, max(0.0, (total - remain) / total))
    if frac > 0.001:
        fg = QPen(QColor(hig["dot_green"]), stroke)
        fg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(fg)
        painter.drawArc(ring_rect, 90 * 16, -int(360 * 16 * frac))


def paint_spectrum(bar: BarWidget, painter: QPainter, rect: QRect, hig: dict) -> None:
    t = time.monotonic()
    color = QColor(hig["now_bar"])
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    bw = max(2.0, 2.6 * bar._scale)
    gap = max(2.0, 3.2 * bar._scale)
    total_w = bw * 3 + gap * 2
    x0 = rect.center().x() - total_w / 2.0
    bottom = rect.center().y() + rect.height() * 0.40
    max_h = rect.height() * 0.80
    still = (0.40, 0.92, 0.62)
    for i in range(3):
        if bar._paused:
            level = still[i]
        else:
            ph = t * (4.6 + i * 1.7) + i * 2.1
            level = 0.32 + 0.68 * (0.5 + 0.5 * math.sin(ph))
        bh = max(bw, max_h * level)
        x = x0 + i * (bw + gap)
        painter.drawRoundedRect(QRectF(x, bottom - bh, bw, bh), bw / 2.0, bw / 2.0)


class ScheduleViewStrategy(BarViewStrategy):
    """日程 + 待办跑马灯 + 专注倒计时常驻条视图策略。"""

    view_id = VIEW_SCHEDULE
    label = VIEW_LABELS[VIEW_SCHEDULE]

    def is_available(self, bar: BarWidget) -> bool:
        return True

    def desired_width(self, bar: BarWidget, h: float, dpr: float) -> int:
        bar._sync_schedule_fonts(h)
        left_pad, _r, _ring_gap, tx = schedule_ring_geometry(bar._scale, h)
        pct_reserve = 44.0 * bar._scale
        need = (
            tx
            + max(bar._text_width_row1(bar._sizing_row1()) + pct_reserve, bar._text_width(bar._row2))
            + left_pad
        )
        max_w = int(bar._cfg["style"].get("width", 330) * dpr)
        min_w = int(96 * dpr)
        return max(min_w, min(int(math.ceil(need)), max_w))

    def paint(self, bar: BarWidget, painter: QPainter, r: QRect) -> None:
        h = float(r.height())
        bar._sync_schedule_fonts(h)
        dark = theme.is_system_dark()
        t = tokens.get_tokens(dark)
        style = bar._cfg["style"]
        s = bar._scale

        left_pad, ring_outer_r, _ring_gap, tx = schedule_ring_geometry(s, h)
        cx = left_pad + ring_outer_r
        cy = h / 2.0
        stroke_w = max(2.0, 2.35 * s)
        ring_r = max(4.0, ring_outer_r - stroke_w / 2.0)
        ring_rect = QRectF(cx - ring_r, cy - ring_r, 2.0 * ring_r, 2.0 * ring_r)

        in_focus = bool(bar._focus_until and time.monotonic() < bar._focus_until)
        now_dt = datetime.datetime.now()
        cur_item = config_mod.current_schedule(bar._cfg, now_dt)

        if in_focus:
            remain = max(0.0, bar._focus_until - time.monotonic())
            total = max(1.0, float(bar._focus_total))
            raw_ratio = max(0.04, min(1.0, remain / total))
            base_c = QColor(t.danger_solid)
            ring_mode = "focus"
            badge_txt = f"{max(1, int(math.ceil(remain / 60.0)))}m"
        elif cur_item is not None:
            raw_ratio = config_mod.schedule_progress(bar._cfg, now_dt)
            base_c = QColor(style.get("scheduleBarColor", t.warn_solid))
            if not base_c.isValid():
                base_c = QColor(t.warn_solid)
            ring_mode = "schedule"
            badge_txt = f"{int(round(raw_ratio * 100))}%"
        else:
            raw_ratio = 1.0
            base_c = QColor(t.ok_solid)
            ring_mode = "free"
            badge_txt = ""

        badge_fg = base_c.lighter(124) if dark else base_c.darker(135)
        badge_bg = QColor(base_c.red(), base_c.green(), base_c.blue(), 34 if dark else 26)
        ratio = bar._display_ring_ratio("schedule:main", raw_ratio)

        # 1. 柔底进度环徽章
        inner_r = max(2.5, ring_r - stroke_w * 0.55)
        disc_c = QColor(base_c)
        disc_c.setAlpha(32 if dark else 24)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(disc_c)
        painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        if dark:
            track_color = QColor(base_c.red(), base_c.green(), base_c.blue(), 52)
        else:
            tr_base = base_c.darker(115)
            track_color = QColor(tr_base.red(), tr_base.green(), tr_base.blue(), 56)
        track_pen = QPen(track_color, stroke_w)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(ring_rect)

        if ratio > 0.005:
            deg = min(360.0, max(6.0, 360.0 * ratio))
            span = int(round(deg * 16))
            arc_grad = QLinearGradient(ring_rect.left(), ring_rect.top(), ring_rect.right(), ring_rect.bottom())
            arc_grad.setColorAt(0.0, base_c.lighter(114) if dark else base_c.lighter(108))
            arc_grad.setColorAt(1.0, base_c if dark else base_c.darker(108))
            arc_pen = QPen(arc_grad, stroke_w)
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(ring_rect, 90 * 16, -span)

        ic_col = base_c.lighter(126) if dark else base_c.darker(128)
        ic_pen = QPen(
            ic_col,
            max(1.3, 1.5 * s),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        if ring_mode == "focus":
            core_r = max(2.0, inner_r * 0.34)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ic_col)
            painter.drawEllipse(QPointF(cx, cy), core_r, core_r)
        elif ring_mode == "free":
            painter.setPen(ic_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            u = inner_r * 0.44
            chk_path = QPainterPath()
            chk_path.moveTo(cx - u * 0.85, cy + u * 0.05)
            chk_path.lineTo(cx - u * 0.15, cy + u * 0.72)
            chk_path.lineTo(cx + u * 0.95, cy - u * 0.62)
            painter.drawPath(chk_path)
        else:
            painter.setPen(ic_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            u = inner_r * 0.50
            painter.drawLine(QPointF(cx, cy), QPointF(cx, cy - u))
            painter.drawLine(QPointF(cx, cy), QPointF(cx + u * 0.70, cy + u * 0.34))

        # 2. 右侧均衡双行排版
        tw = max(24.0, float(r.width()) - tx - left_pad)
        fm1 = bar._fm1()
        fm2 = bar._fm()
        h1 = optical_line_height(bar._font_row1, fm1)
        h2 = optical_line_height(bar._font_row2, fm2)
        fs_norm = (max(8, min(16, int(style.get("fontSize", 10)))) - 8) / 8.0
        line_gap = max(1.0, (2.2 - 0.8 * fs_norm) * s)
        block_h = h1 + h2 + line_gap
        top_y = (h - block_h) / 2.0
        sub_rect = QRectF(tx, top_y + h1 + line_gap, tw, h2)

        right_tag = "\u23f8" if bar._paused else badge_txt
        pill_gap = 6.5 * s
        pill_pad_x = 5.0 * s
        pill_w = 0.0
        f_tag = None
        if right_tag:
            f_tag = QFont()
            f_tag.setFamilies(preferred_families(style, display=True))
            f_tag.setPixelSize(max(9, int(round(bar._font_row2.pixelSize() * 0.88))))
            f_tag.setWeight(QFont.Weight.DemiBold)
            fm_tag = QFontMetrics(f_tag)
            pill_w = float(fm_tag.horizontalAdvance(right_tag)) + pill_pad_x * 2.0

        title_avail = max(16.0, tw - (pill_w + pill_gap if pill_w > 0.0 else 0.0))
        elided_title = fm1.elidedText(bar._row1, Qt.TextElideMode.ElideRight, int(title_avail))
        actual_title_w = min(title_avail, float(fm1.horizontalAdvance(elided_title)))

        clip_pad_y = max(3.0, 3.0 * s)
        painter.save()
        painter.setClipRect(QRectF(tx, top_y - clip_pad_y, title_avail + 1.0, h1 + clip_pad_y * 2.0))
        painter.setFont(bar._font_row1)
        painter.setPen(bar._row1_color)
        painter.drawText(
            QRectF(tx, top_y, title_avail, h1),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided_title,
        )
        painter.restore()

        if right_tag and f_tag is not None and pill_w > 0.0:
            pill_h = max(12.0, h1 * 0.72)
            pill_x = min(tx + actual_title_w + pill_gap, tx + tw - pill_w)
            pill_y = top_y + (h1 - pill_h) / 2.0 + 0.4
            pill_rect = QRectF(pill_x, pill_y, pill_w, pill_h)
            pill_r = pill_h / 2.0
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(badge_bg)
            painter.drawRoundedRect(pill_rect, pill_r, pill_r)
            painter.setFont(f_tag)
            painter.setPen(badge_fg)
            painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, right_tag)

        row2_pad = max(2, int(round(2.0 * s)))
        row2_rect = QRect(
            int(round(sub_rect.x())),
            int(round(sub_rect.y())) - row2_pad,
            max(20, int(round(sub_rect.width()))),
            max(1, int(round(sub_rect.height())) + row2_pad * 2),
        )
        sub_color = QColor(t.text_secondary) if style.get("autoColor", True) else QColor(bar._row2_color)

        painter.save()
        painter.setClipRect(row2_rect)
        painter.setFont(bar._font_row2)
        painter.setPen(sub_color)
        text_w = bar._text_width(bar._row2)
        if text_w <= row2_rect.width():
            painter.drawText(
                QRectF(row2_rect),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                bar._row2,
            )
        else:
            paint_scrolling_row2(bar, painter, row2_rect, sub_color)
        painter.restore()
