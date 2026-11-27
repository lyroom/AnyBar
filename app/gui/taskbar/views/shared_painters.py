"""app/gui/taskbar/views/shared_painters.py — 常驻条公共液态玻璃表面、字体栈与度量原语"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen

from app.gui.widgets import motion
from app.styles import theme, tokens

if TYPE_CHECKING:
    from app.gui.taskbar.widget import BarWidget


def preferred_families(cfg_style: dict, display: bool = False) -> list[str]:
    """构造原生 Win11 字体栈：默认字体时让 Segoe UI Variable 优先渲染拉丁与数字，中文平滑回退雅黑。"""
    family = str(cfg_style.get("fontFamily", "Microsoft YaHei UI") or "Microsoft YaHei UI").strip()
    win11 = (
        ["Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI"]
        if display
        else ["Segoe UI Variable Text", "Segoe UI Variable Display", "Segoe UI"]
    )
    if family.lower() in ("microsoft yahei ui", "microsoft yahei", "segoe ui", ""):
        return [*win11, "Microsoft YaHei UI", "Segoe UI Emoji"]
    return [family, *win11, "Microsoft YaHei UI", "Segoe UI Emoji"]


def build_bar_fonts(cfg_style: dict, scale: float, h: float) -> tuple[QFont, QFont]:
    """根据任务栏高度 h 与字号档位（8~16）线性生成上下行字体。"""
    s = max(1.0, float(scale or 1.0))
    font_size = max(8, min(16, int(cfg_style.get("fontSize", 10))))
    t_norm = (font_size - 8) / 8.0
    inset_y = max(2.5, 3.0 * s)
    inner_h = max(20.0, float(h) - inset_y * 2.0)

    top_px = max(10, int(round(inner_h * (0.28 + 0.175 * t_norm))))
    sub_px = max(9, int(round(inner_h * (0.215 + 0.135 * t_norm))))
    sub_px = min(sub_px, max(9, top_px - max(2, int(round(2.0 * s)))))

    use_bold = bool(cfg_style.get("bold", True))
    fams = preferred_families(cfg_style, display=False)
    f1 = QFont()
    f1.setFamilies(fams)
    f1.setPixelSize(top_px)
    f1.setWeight(QFont.Weight.Bold if use_bold else QFont.Weight.Medium)
    f2 = QFont()
    f2.setFamilies(fams)
    f2.setPixelSize(sub_px)
    f2.setWeight(QFont.Weight.Medium if use_bold else QFont.Weight.Normal)
    return f1, f2


def telemetry_fonts(cfg_style: dict, scale: float, h: float) -> tuple[QFont, QFont]:
    """算力 / 硬件线型遥测视图专用字体：与 8~16 字号档位线性同步。"""
    s = max(1.0, float(scale or 1.0))
    font_size = max(8, min(16, int(cfg_style.get("fontSize", 10))))
    t_norm = (font_size - 8) / 8.0
    inset_y = max(2.5, 3.0 * s)
    inner_h = max(20.0, float(h) - inset_y * 2.0)
    px = max(10, int(round(inner_h * (0.28 + 0.14 * t_norm))))
    use_bold = bool(cfg_style.get("bold", True))

    f_name = QFont()
    f_name.setFamilies(preferred_families(cfg_style, display=False))
    f_name.setPixelSize(px)
    f_name.setWeight(QFont.Weight.Bold if use_bold else QFont.Weight.Medium)

    f_val = QFont()
    f_val.setFamilies(preferred_families(cfg_style, display=True))
    f_val.setPixelSize(px)
    f_val.setWeight(QFont.Weight.Bold if use_bold else QFont.Weight.DemiBold)
    return f_name, f_val


def optical_line_height(font: QFont, fm: QFontMetrics) -> float:
    """按实际字形高度估算紧致光学行高，避免高行距字体的隐形空气过早挤爆双行布局。"""
    px = float(font.pixelSize())
    return min(float(fm.height()), max(px * 1.12, float(fm.ascent()) + float(fm.descent()) * 0.45))


def schedule_ring_geometry(scale: float, h: float) -> tuple[float, float, float, float]:
    """日程视图左侧进度徽章统一度量：(left_pad, R, ring_gap, tx)，供绘制/测宽/滚动共用。"""
    s = max(1.0, float(scale or 1.0))
    left_pad = 11.0 * s
    r_val = max(8.5, float(h) * 0.235)
    ring_gap = 9.5 * s
    tx = left_pad + 2.0 * r_val + ring_gap
    return left_pad, r_val, ring_gap, tx


def paint_liquid_glass_island(bar: BarWidget, painter: QPainter, r: QRect) -> QRectF:
    """原生 Win11 Fluent 融入式表面：常态隐融于任务栏无贴片框感，悬停平滑绽放 Fluent 磨砂高亮。

    常态在 glass_rect 内严格保持 alpha >= 30（高于 Win32 WS_EX_LAYERED 的 28 命中门槛）。
    """
    dark = theme.is_system_dark()
    t = tokens.get_tokens(dark)
    style = bar._cfg["style"]
    hv = motion.ease_out_cubic(bar._hover_progress)
    s = bar._scale

    inset_x = max(1.0, 1.5 * s)
    inset_y = max(2.5, 3.0 * s)
    radius = max(5.0, 6.0 * s)
    glass_rect = QRectF(r).adjusted(inset_x, inset_y, -inset_x, -inset_y)

    if hv > 0.02 and style.get("bgMode") != "color":
        shadow_rect = glass_rect.adjusted(0.0, 0.8, 0.0, 1.2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, int((22 if dark else 10) * hv)))
        painter.drawRoundedRect(shadow_rect, radius, radius)

    painter.setPen(Qt.PenStyle.NoPen)
    if style.get("bgMode") == "color":
        painter.setBrush(QColor(style.get("bgColor", "#1F1F1F")))
        painter.drawRoundedRect(glass_rect, radius, radius)
    else:
        if bar._tb_color:
            tb_r, tb_g, tb_b = bar._tb_color
            rest_top = QColor(tb_r, tb_g, tb_b, 30)
            rest_bot = QColor(tb_r, tb_g, tb_b, 30)
        else:
            rest_top = QColor(28, 31, 38, 32) if dark else QColor(242, 245, 249, 30)
            rest_bot = QColor(24, 27, 34, 32) if dark else QColor(240, 243, 248, 30)

        if dark:
            hov_top = QColor(56, 61, 74, 152)
            hov_bot = QColor(42, 46, 56, 132)
        else:
            hov_top = QColor(255, 255, 255, 194)
            hov_bot = QColor(248, 250, 253, 156)

        body_grad = QLinearGradient(0.0, glass_rect.top(), 0.0, glass_rect.bottom())
        body_grad.setColorAt(0.0, motion.blend_color(rest_top, hov_top, hv))
        body_grad.setColorAt(1.0, motion.blend_color(rest_bot, hov_bot, hv))
        painter.setBrush(body_grad)
        painter.drawRoundedRect(glass_rect, radius, radius)

    if bar._glow_active:
        glow_color = QColor(t.warn_solid)
        amp = 10 + 12 * (0.5 + 0.5 * math.sin(bar._glow_phase))
        glow_color.setAlpha(int(amp))
        painter.setBrush(glow_color)
        painter.drawRoundedRect(glass_rect, radius, radius)

    if hv > 0.02 and style.get("bgMode") != "color":
        rim_grad = QLinearGradient(0.0, glass_rect.top(), 0.0, glass_rect.bottom())
        if dark:
            rim_grad.setColorAt(0.0, QColor(255, 255, 255, int(50 * hv)))
            rim_grad.setColorAt(1.0, QColor(255, 255, 255, int(14 * hv)))
        else:
            rim_grad.setColorAt(0.0, QColor(255, 255, 255, int(230 * hv)))
            rim_grad.setColorAt(1.0, QColor(15, 23, 42, int(24 * hv)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(rim_grad, 1.0))
        painter.drawRoundedRect(
            glass_rect.adjusted(0.5, 0.5, -0.5, -0.5),
            max(4.0, radius - 0.5),
            max(4.0, radius - 0.5),
        )
    return glass_rect
