"""app/gui/taskbar/views/tiles_view.py — 算力套餐 / 系统硬件线型遥测视图策略"""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QLinearGradient, QPainter, QPen, QRadialGradient

from app.styles import theme, tokens

from . import BarViewStrategy, VIEW_QUOTA, VIEW_SYSTEM
from .shared_painters import telemetry_fonts

if TYPE_CHECKING:
    from app.gui.taskbar.widget import BarWidget


def tile_display_value(q: dict, is_sys: bool) -> str:
    """提炼线型遥测视图右侧最简洁的单值展示（消除双重百分比冗余）。"""
    if is_sys:
        return str(q.get("center_text") or f"{int(round(float(q.get('frac', 0.0)) * 100))}%")
    center = str(q.get("center_text") or "").strip()
    sub = str(q.get("sub_text") or "").strip()
    if center in ("¥", "$", "积分", "0") and sub:
        return sub
    if center.endswith("%"):
        return center
    return sub or center or "—"


def compute_tiles_layout(bar: BarWidget, w: int, h: float, is_sys: bool | None = None):
    """现代线型遥测列布局测算：状态微点 + 完整名称 + 右对齐数值 + 下方极细进度条。"""
    quotas = bar.current_tiles()
    n = len(quotas)
    if not n:
        return [], 0.0
    s = bar._scale
    if is_sys is None:
        is_sys = bar.is_system_view()
    f_name, f_val = telemetry_fonts(bar._cfg["style"], s, h)
    fm_name = QFontMetrics(f_name)
    fm_val = QFontMetrics(f_val)

    outer_pad = 12.0 * s
    item_gap = 16.0 * s
    dot_slot = (9.5 * s) if not is_sys else 0.0
    val_gap = 7.5 * s
    min_col = (64.0 if is_sys else 72.0) * s
    max_col = (102.0 if is_sys else 138.0) * s

    col_widths = []
    val_texts = []
    val_widths = []
    for q in quotas:
        name_s = str(q.get("name", ""))
        val_s = tile_display_value(q, is_sys)
        nw = float(fm_name.horizontalAdvance(name_s))
        vw = float(fm_val.horizontalAdvance(val_s))
        cw = max(min_col, min(max_col, dot_slot + nw + val_gap + vw + 2.0 * s))
        col_widths.append(cw)
        val_texts.append(val_s)
        val_widths.append(vw)

    total_content = sum(col_widths) + item_gap * (n - 1)
    total = total_content + outer_pad * 2.0

    if w > 0:
        avail = max(60.0, float(w) - outer_pad * 2.0)
        if avail < total_content:
            ratio = avail / max(1.0, total_content)
            item_gap_draw = max(8.0 * s, item_gap * ratio)
            draw_ws = [max(44.0 * s, cw * ratio) for cw in col_widths]
            total_draw = sum(draw_ws) + item_gap_draw * (n - 1)
            x = max(outer_pad * 0.6, (float(w) - total_draw) / 2.0)
        else:
            item_gap_draw = item_gap
            draw_ws = col_widths
            x = max(outer_pad, (float(w) - total_content) / 2.0)
    else:
        item_gap_draw = item_gap
        draw_ws = col_widths
        x = outer_pad

    cells = []
    for idx, q in enumerate(quotas):
        cw = draw_ws[idx]
        sep_x = (x + cw + item_gap_draw / 2.0) if idx < n - 1 else None
        cells.append({
            "x": x, "w": cw, "q": q,
            "val_text": val_texts[idx], "val_w": val_widths[idx],
            "dot_slot": dot_slot, "sep_x": sep_x,
        })
        x += cw + item_gap_draw
    return cells, total


class TilesViewStrategy(BarViewStrategy):
    """可复用的线型遥测指标视图策略（同时支撑系统硬件视图与算力套餐视图）。"""

    def __init__(self, view_id: str, label: str, is_system: bool) -> None:
        self.view_id = view_id
        self.label = label
        self._is_system = bool(is_system)

    def is_available(self, bar: BarWidget) -> bool:
        if self._is_system:
            src_cfg = bar._cfg.get("sources") or {}
            return bool(src_cfg.get("system", {}).get("enabled", True) and bar._source_tiles.get("system"))
        return bool(bar._valid_quotas())

    def desired_width(self, bar: BarWidget, h: float, dpr: float) -> int:
        _, total = compute_tiles_layout(bar, 0, h, is_sys=self._is_system)
        cfg_w = int(bar._cfg["style"].get("width", 330))
        max_w = int(max(cfg_w, 580) * dpr)
        return max(int(96 * dpr), min(int(math.ceil(total)), max_w))

    def paint(self, bar: BarWidget, painter: QPainter, r: QRect) -> None:
        h = float(r.height())
        is_sys = self._is_system
        cells, _total = compute_tiles_layout(bar, r.width(), h, is_sys=is_sys)
        if not cells:
            return
        dark = theme.is_system_dark()
        t = tokens.get_tokens(dark)
        s = bar._scale

        f_name, f_val = telemetry_fonts(bar._cfg["style"], s, h)
        fm_name = QFontMetrics(f_name)

        name_color = QColor(t.text)
        track_color = QColor(255, 255, 255, 28) if dark else QColor(15, 23, 42, 20)
        depleted_track = QColor(248, 113, 113, 42) if dark else QColor(220, 38, 38, 30)
        sep_color = QColor(255, 255, 255, 20) if dark else QColor(15, 23, 42, 16)

        bar_h = max(3.6, 4.0 * s)
        bar_gap = max(4.0, 4.8 * s)
        text_h = float(max(fm_name.height(), QFontMetrics(f_val).height()))
        block_h = text_h + bar_gap + bar_h
        top_y = (h - block_h) / 2.0
        bar_y = top_y + text_h + bar_gap
        dot_r = max(2.6, 2.9 * s)
        now_mono = time.monotonic()
        sheen = bar._hover_sheen

        for idx, c in enumerate(cells):
            q = c["q"]
            x = float(c["x"])
            cw = float(c["w"])
            val_txt = str(c["val_text"])
            val_w = min(float(c["val_w"]), cw * 0.56)
            dot_slot = float(c["dot_slot"])

            raw_val = q["ratio"] if q.get("ratio") is not None else q.get("frac", 0.0)
            raw_ratio = float(raw_val)
            ring_key = f"{'sys' if is_sys else 'quota'}:{q.get('id') or q.get('name') or idx}"
            ratio = bar._display_ring_ratio(ring_key, raw_ratio)
            is_urgent = (not is_sys) and (raw_ratio <= 0.20)

            if is_sys:
                bar_c = QColor(tokens.load_tier_color(raw_ratio, dark))
                if raw_ratio > 0.88:
                    val_c = QColor(t.danger)
                elif raw_ratio > 0.75:
                    val_c = QColor(t.warn)
                else:
                    val_c = QColor(t.text_secondary)
            else:
                bar_hex, val_hex = tokens.quota_tier_colors(raw_ratio, dark)
                bar_c = QColor(bar_hex)
                val_c = QColor(val_hex) if raw_ratio <= 0.50 else QColor(t.text_secondary)

            name_x = x
            if dot_slot > 0.0:
                dot_cy = top_y + text_h / 2.0 + 0.4
                dot_cx = x + dot_r + 0.4
                painter.setPen(Qt.PenStyle.NoPen)
                if is_urgent:
                    pulse = 0.5 + 0.5 * math.sin(now_mono * 3.4)
                    hr = dot_r + (2.0 + 1.8 * pulse) * s
                    halo = QRadialGradient(dot_cx, dot_cy, hr)
                    halo.setColorAt(0.0, QColor(bar_c.red(), bar_c.green(), bar_c.blue(), int(115 + 80 * pulse)))
                    halo.setColorAt(1.0, QColor(bar_c.red(), bar_c.green(), bar_c.blue(), 0))
                    painter.setBrush(halo)
                    painter.drawEllipse(QPointF(dot_cx, dot_cy), hr, hr)
                elif dark or bar._hover_progress > 0.05:
                    hr = dot_r + 1.8 * s
                    halo = QRadialGradient(dot_cx, dot_cy, hr)
                    halo.setColorAt(
                        0.0,
                        QColor(bar_c.red(), bar_c.green(), bar_c.blue(), 68 if dark else int(65 * bar._hover_progress)),
                    )
                    halo.setColorAt(1.0, QColor(bar_c.red(), bar_c.green(), bar_c.blue(), 0))
                    painter.setBrush(halo)
                    painter.drawEllipse(QPointF(dot_cx, dot_cy), hr, hr)

                bead = QRadialGradient(dot_cx - dot_r * 0.30, dot_cy - dot_r * 0.30, dot_r * 1.45)
                bead.setColorAt(0.0, bar_c.lighter(152))
                bead.setColorAt(0.48, bar_c)
                bead.setColorAt(1.0, bar_c.darker(118))
                painter.setBrush(bead)
                painter.drawEllipse(QPointF(dot_cx, dot_cy), dot_r, dot_r)
                name_x = x + dot_slot

            avail_name_w = max(14.0, cw - (name_x - x) - val_w - 5.0 * s)
            painter.setFont(f_name)
            painter.setPen(name_color)
            painter.drawText(
                QRectF(name_x, top_y, avail_name_w, text_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                fm_name.elidedText(str(q.get("name", "")), Qt.TextElideMode.ElideRight, int(avail_name_w)),
            )

            painter.setFont(f_val)
            painter.setPen(val_c)
            painter.drawText(
                QRectF(x + cw - val_w - 1.0, top_y, val_w + 2.0, text_h),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                val_txt,
            )

            bar_r = bar_h / 2.0
            track_rect = QRectF(x, bar_y, cw, bar_h)
            painter.setPen(Qt.PenStyle.NoPen)
            cur_track = depleted_track if (not is_sys and raw_ratio <= 0.005) else track_color
            tgrad = QLinearGradient(x, bar_y, x, bar_y + bar_h)
            if dark:
                tgrad.setColorAt(0.0, QColor(0, 0, 0, 82))
                tgrad.setColorAt(1.0, cur_track)
            else:
                tgrad.setColorAt(0.0, QColor(15, 23, 42, 42))
                tgrad.setColorAt(1.0, QColor(255, 255, 255, 95))
            painter.setBrush(tgrad)
            painter.drawRoundedRect(track_rect, bar_r, bar_r)

            if ratio > 0.008:
                fill_w = max(bar_h, cw * ratio)
                fill_rect = QRectF(x, bar_y, fill_w, bar_h)
                grad = QLinearGradient(x, bar_y, x + fill_w, bar_y)
                grad.setColorAt(0.0, bar_c.darker(106))
                grad.setColorAt(0.65, bar_c)
                grad.setColorAt(1.0, bar_c.lighter(120))
                painter.setBrush(grad)
                painter.drawRoundedRect(fill_rect, bar_r, bar_r)

                hl_h = max(1.1, bar_h * 0.44)
                hl = QLinearGradient(0.0, bar_y, 0.0, bar_y + hl_h)
                hl.setColorAt(0.0, QColor(255, 255, 255, 132 if not dark else 96))
                hl.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.setBrush(hl)
                painter.drawRoundedRect(
                    QRectF(x + 0.6, bar_y + 0.25, max(1.0, fill_w - 1.2), hl_h),
                    hl_h / 2.0,
                    hl_h / 2.0,
                )

                if -0.25 < sheen < 1.25 and fill_w > bar_h * 1.5:
                    sx_c = x + fill_w * sheen
                    band = max(16.0 * s, fill_w * 0.36)
                    sg = QLinearGradient(sx_c - band, bar_y, sx_c + band, bar_y)
                    sg.setColorAt(0.0, QColor(255, 255, 255, 0))
                    sg.setColorAt(0.5, QColor(255, 255, 255, 140))
                    sg.setColorAt(1.0, QColor(255, 255, 255, 0))
                    painter.setBrush(sg)
                    painter.drawRoundedRect(fill_rect, bar_r, bar_r)

                if 0.05 < ratio < 0.995:
                    tip_x = x + fill_w - bar_r
                    tip_y = bar_y + bar_r
                    tg = QRadialGradient(tip_x, tip_y, bar_r * 1.45)
                    tg.setColorAt(0.0, QColor(255, 255, 255, 160))
                    tg.setColorAt(1.0, QColor(255, 255, 255, 0))
                    painter.setBrush(tg)
                    painter.drawEllipse(QPointF(tip_x, tip_y), bar_r * 1.1, bar_r * 1.1)

            if c.get("sep_x") is not None:
                sx = float(c["sep_x"])
                painter.setPen(QPen(sep_color, 1.0))
                painter.drawLine(QPointF(sx, h * 0.30), QPointF(sx, h * 0.70))
