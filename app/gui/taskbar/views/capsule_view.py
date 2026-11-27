"""app/gui/taskbar/views/capsule_view.py — 微型双列胶囊渲染器（表驱动槽位分发）"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen

from app.styles import theme, tokens
from app.styles.weather_glyph import kind_from_emoji, paint_weather_glyph

from .shared_painters import paint_liquid_glass_island, preferred_families
from .weather_view import weather_temp_text

if TYPE_CHECKING:
    from app.gui.taskbar.widget import BarWidget


@dataclass(frozen=True)
class _SlotContext:
    bar: BarWidget
    painter: QPainter
    x_start: float
    slot_w: float
    h: float
    dark: bool
    font: QFont
    fm: QFontMetrics
    primary: QColor
    gap: float


def _draw_ring_and_text(ctx: _SlotContext, ratio: float, pct_s: str, color_hex: str, key: str) -> None:
    t = tokens.get_tokens(ctx.dark)
    track_c = QColor(*t.track_alpha)
    ring_r = max(4.5, ctx.h * 0.20)
    ring_pen_w = max(1.8, 2.0 * ctx.bar._scale)
    disp_r = ctx.bar._display_ring_ratio(key, ratio)
    pct_w = ctx.fm.horizontalAdvance(pct_s)
    total_w = (ring_r * 2.0) + ctx.gap + pct_w
    rx = ctx.x_start + max(2.0, (ctx.slot_w - total_w) / 2.0)
    rcx = rx + ring_r
    rcy = ctx.h / 2.0

    ctx.painter.setPen(QPen(track_c, ring_pen_w))
    ctx.painter.setBrush(Qt.BrushStyle.NoBrush)
    ctx.painter.drawEllipse(QPointF(rcx, rcy), ring_r, ring_r)

    prog_pen = QPen(QColor(color_hex), ring_pen_w)
    prog_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    ctx.painter.setPen(prog_pen)
    span = int(-disp_r * 360 * 16)
    ctx.painter.drawArc(QRectF(rcx - ring_r, rcy - ring_r, ring_r * 2.0, ring_r * 2.0), 90 * 16, span)

    ctx.painter.setFont(ctx.font)
    ctx.painter.setPen(ctx.primary)
    ctx.painter.drawText(
        QRectF(rx + ring_r * 2.0 + ctx.gap, 0, pct_w + 4, ctx.h),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        pct_s,
    )


def _paint_slot_weather(ctx: _SlotContext) -> None:
    w_tiles = ctx.bar._source_tiles.get("weather") or []
    t_w = w_tiles[0] if w_tiles else {}
    winfo = t_w.get("weather_info") or {}
    kind = winfo.get("kind") or kind_from_emoji(str(winfo.get("icon") or ""))
    temp_s = weather_temp_text(w_tiles)

    glyph_s = max(13.0, ctx.h * 0.50)
    temp_w = ctx.fm.horizontalAdvance(temp_s)
    left_total = glyph_s + ctx.gap + temp_w
    lx = ctx.x_start + max(2.0, (ctx.slot_w - left_total) / 2.0)

    paint_weather_glyph(
        ctx.painter,
        QRectF(lx, (ctx.h - glyph_s) / 2.0, glyph_s, glyph_s),
        kind,
        ctx.dark,
        bool(winfo.get("is_day", True)),
    )
    ctx.painter.setFont(ctx.font)
    ctx.painter.setPen(ctx.primary)
    ctx.painter.drawText(
        QRectF(lx + glyph_s + ctx.gap, 0, temp_w + 4, ctx.h),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        temp_s,
    )


def _paint_slot_ram(ctx: _SlotContext) -> None:
    t = tokens.get_tokens(ctx.dark)
    sys_tiles = ctx.bar._source_tiles.get("system") or []
    t_ram = next((x for x in sys_tiles if x.get("name") == "RAM"), None)
    if t_ram is None and len(sys_tiles) > 1:
        t_ram = sys_tiles[1]
    t_ram = t_ram or {}
    ratio = float(t_ram.get("ratio", 0.45))
    pct_s = str(t_ram.get("center_text") or f"{int(round(ratio * 100))}%")
    color_hex = str(t_ram.get("color") or t.ok_solid)
    _draw_ring_and_text(ctx, ratio, pct_s, color_hex, "capsule:ram")


def _paint_slot_quota(ctx: _SlotContext) -> None:
    t = tokens.get_tokens(ctx.dark)
    quotas = ctx.bar._valid_quotas()
    t_q = quotas[0] if quotas else {}
    ratio = float(t_q.get("ratio", 1.0))
    pct_s = str(t_q.get("center_text") or f"{int(round(ratio * 100))}%")
    color_hex = str(t_q.get("color") or t.ok_solid)
    _draw_ring_and_text(ctx, ratio, pct_s, color_hex, "capsule:quota")


def _paint_slot_net(ctx: _SlotContext) -> None:
    sys_tiles = ctx.bar._source_tiles.get("system") or []
    t0 = sys_tiles[0] if sys_tiles else {}
    down_s = str(t0.get("net_down_str") or "-- B/s")
    short_s = down_s.replace("/s", "").strip()
    net_s = f"↓{short_s}"
    txt_w = ctx.fm.horizontalAdvance(net_s)
    nx = ctx.x_start + max(2.0, (ctx.slot_w - txt_w) / 2.0)
    ctx.painter.setFont(ctx.font)
    ctx.painter.setPen(ctx.primary)
    ctx.painter.drawText(
        QRectF(nx, 0, txt_w + 4, ctx.h),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        net_s,
    )


def _paint_slot_dev(ctx: _SlotContext) -> None:
    t = tokens.get_tokens(ctx.dark)
    dev_tiles = ctx.bar._source_tiles.get("dev") or []
    t_dev = dev_tiles[0] if dev_tiles else {}
    branch = str(t_dev.get("branch") or "git")
    b_short = branch if len(branch) <= 6 else branch[:5] + "…"
    dirty = int(t_dev.get("dirty_count") or 0)
    txt = f"{b_short}*" if dirty > 0 else b_short
    dot_col = QColor(str(t_dev.get("color") or t.ok_solid))
    txt_w = ctx.fm.horizontalAdvance(txt)
    dot_r = max(2.5, 3.0 * ctx.bar._scale)
    total_w = dot_r * 2.0 + ctx.gap + txt_w
    dx = ctx.x_start + max(2.0, (ctx.slot_w - total_w) / 2.0)

    ctx.painter.setPen(Qt.PenStyle.NoPen)
    ctx.painter.setBrush(dot_col)
    ctx.painter.drawEllipse(QPointF(dx + dot_r, ctx.h / 2.0), dot_r, dot_r)

    ctx.painter.setFont(ctx.font)
    ctx.painter.setPen(ctx.primary)
    ctx.painter.drawText(
        QRectF(dx + dot_r * 2.0 + ctx.gap, 0, txt_w + 4, ctx.h),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        txt,
    )


def _paint_slot_cpu(ctx: _SlotContext) -> None:
    t = tokens.get_tokens(ctx.dark)
    sys_tiles = ctx.bar._source_tiles.get("system") or []
    t_cpu = sys_tiles[0] if sys_tiles else {}
    ratio = float(t_cpu.get("ratio", 0.25))
    pct_s = str(t_cpu.get("center_text") or f"{int(round(ratio * 100))}%")
    color_hex = str(t_cpu.get("color") or t.accent)
    _draw_ring_and_text(ctx, ratio, pct_s, color_hex, "capsule:cpu")


CAPSULE_SLOT_PAINTERS: dict[str, Callable[[_SlotContext], None]] = {
    "weather": _paint_slot_weather,
    "ram": _paint_slot_ram,
    "quota": _paint_slot_quota,
    "net": _paint_slot_net,
    "dev": _paint_slot_dev,
    "cpu": _paint_slot_cpu,
}


class CapsuleViewRenderer:
    """微型双列胶囊渲染器：仅占用 ~128px 极窄宽度，左右双槽按表驱动自由搭配。"""

    def paint(self, bar: BarWidget, painter: QPainter, r: QRect) -> None:
        paint_liquid_glass_island(bar, painter, r)

        w = float(r.width())
        h = float(r.height())
        dark = theme.is_system_dark()
        cx = w / 2.0

        sep_col = QColor(255, 255, 255, 22) if dark else QColor(15, 23, 42, 18)
        painter.setPen(QPen(sep_col, max(1.0, 1.0 * bar._scale)))
        painter.drawLine(QPointF(cx, h * 0.28), QPointF(cx, h * 0.72))

        primary = QColor(bar._row1_color)
        style = bar._cfg.get("style", {})
        use_bold = bool(style.get("bold", True))
        f_font = QFont()
        f_font.setFamilies(preferred_families(style, display=True))
        f_font.setPixelSize(max(11, int(round(h * 0.305))))
        f_font.setWeight(QFont.Weight.Bold if use_bold else QFont.Weight.DemiBold)
        painter.setFont(f_font)
        fm = painter.fontMetrics()

        gap = 4.5 * bar._scale
        left_type = str(style.get("capsuleLeft", "weather"))
        right_type = str(style.get("capsuleRight", "cpu"))

        left_ctx = _SlotContext(bar, painter, 0.0, cx, h, dark, f_font, fm, primary, gap)
        right_ctx = _SlotContext(bar, painter, cx, w - cx, h, dark, f_font, fm, primary, gap)

        CAPSULE_SLOT_PAINTERS.get(left_type, _paint_slot_cpu)(left_ctx)
        CAPSULE_SLOT_PAINTERS.get(right_type, _paint_slot_cpu)(right_ctx)
