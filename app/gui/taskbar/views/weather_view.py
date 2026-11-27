"""app/gui/taskbar/views/weather_view.py — 实时天气常驻条视图策略"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter

from app.styles import theme, tokens
from app.styles.weather_glyph import kind_from_emoji, paint_weather_glyph

from . import BarViewStrategy, VIEW_LABELS, VIEW_WEATHER
from .shared_painters import preferred_families

if TYPE_CHECKING:
    from app.gui.taskbar.widget import BarWidget


def format_weather_texts(weather_tiles: list[dict]) -> tuple[str, str]:
    """按天气数据格式化双行展示文本（主行: 城市·天气状况，副行: 高低温·湿度·风向）。"""
    if not weather_tiles:
        return "实时天气 · 正在同步", "请稍候或检查网络连接"
    t0 = weather_tiles[0]
    winfo = t0.get("weather_info") or {}
    city = winfo.get("city") or t0.get("name") or "当地"
    cond = winfo.get("condition") or t0.get("sub_text") or "晴"
    row1 = f"{city} · {cond}"

    parts = []
    max_t = winfo.get("max_temp_c")
    min_t = winfo.get("min_temp_c")
    if max_t is not None and min_t is not None:
        parts.append(f"↑{int(round(max_t))}° ↓{int(round(min_t))}°")
    if "humidity" in winfo:
        parts.append(f"湿度 {int(round(winfo['humidity']))}%")
    wind_d = (winfo.get("wind_dir") or "").replace("风", "")[:2]
    wind_s = winfo.get("wind_speed_kmh")
    if wind_d or wind_s:
        parts.append(f"{wind_d} {int(round(wind_s))}km/h".strip() if wind_s else wind_d)

    row2 = " · ".join(parts) if parts else "实时气象数据已更新"
    return row1, row2


def weather_temp_text(weather_tiles: list[dict]) -> str:
    return str((weather_tiles[0] if weather_tiles else {}).get("center_text") or "--°")


def weather_metrics(cfg_style: dict, scale: float, h: float) -> dict:
    """天气视图的统一度量（绘制与 desired_width 共用）。"""
    use_bold = bool(cfg_style.get("bold", True))
    f_temp = QFont()
    f_temp.setFamilies(preferred_families(cfg_style, display=True))
    f_temp.setPixelSize(max(13, int(round(h * 0.50))))
    f_temp.setWeight(QFont.Weight.Bold if use_bold else QFont.Weight.DemiBold)
    f1 = QFont()
    f1.setFamilies(preferred_families(cfg_style, display=False))
    f1.setPixelSize(max(11, int(round(h * 0.295))))
    f1.setWeight(QFont.Weight.Bold if use_bold else QFont.Weight.Medium)
    f2 = QFont(f1)
    f2.setPixelSize(max(10, int(round(h * 0.25))))
    f2.setWeight(QFont.Weight.Medium if use_bold else QFont.Weight.Normal)
    return {
        "pad": 11.0 * scale,
        "glyph": h * 0.64,
        "gap1": 7.5 * scale,
        "gap2": 10.5 * scale,
        "f_temp": f_temp,
        "f1": f1,
        "f2": f2,
    }


class WeatherViewStrategy(BarViewStrategy):
    """矢量天气图标 + 大号气温 + 双行气象详情视图策略。"""

    view_id = VIEW_WEATHER
    label = VIEW_LABELS[VIEW_WEATHER]

    def is_available(self, bar: BarWidget) -> bool:
        src_cfg = bar._cfg.get("sources") or {}
        return bool(src_cfg.get("weather", {}).get("enabled", True) and bar._source_tiles.get("weather"))

    def desired_width(self, bar: BarWidget, h: float, dpr: float) -> int:
        w_tiles = bar._source_tiles.get("weather") or []
        m = weather_metrics(bar._cfg["style"], bar._scale, h)
        temp_w = QFontMetrics(m["f_temp"]).horizontalAdvance(weather_temp_text(w_tiles))
        r1, r2 = format_weather_texts(w_tiles)
        text_w = max(QFontMetrics(m["f1"]).horizontalAdvance(r1), QFontMetrics(m["f2"]).horizontalAdvance(r2))
        need = m["pad"] + m["glyph"] + m["gap1"] + temp_w + m["gap2"] + text_w + 8.0 * bar._scale + m["pad"]
        max_w = int(max(int(bar._cfg["style"].get("width", 330)), 400) * dpr)
        min_w = int(120 * dpr)
        return max(min_w, min(int(math.ceil(need)), max_w))

    def paint(self, bar: BarWidget, painter: QPainter, r: QRect) -> None:
        h = float(r.height())
        dark = theme.is_system_dark()
        t = tokens.get_tokens(dark)
        m = weather_metrics(bar._cfg["style"], bar._scale, h)

        w_tiles = bar._source_tiles.get("weather") or []
        t0 = w_tiles[0] if w_tiles else {}
        winfo = t0.get("weather_info") or {}
        kind = winfo.get("kind") or kind_from_emoji(str(winfo.get("icon") or ""))

        primary = QColor(bar._row1_color)
        secondary = QColor(t.text_secondary) if bar._cfg["style"].get("autoColor", True) else QColor(bar._row2_color)

        x = m["pad"]
        g = m["glyph"]
        paint_weather_glyph(
            painter,
            QRectF(x, (h - g) / 2.0, g, g),
            kind,
            dark,
            bool(winfo.get("is_day", True)),
            phase=bar._weather_phase if bar._hover else 0.0,
        )
        x += g + m["gap1"]

        temp_text = weather_temp_text(w_tiles)
        fm_t = QFontMetrics(m["f_temp"])
        temp_w = fm_t.horizontalAdvance(temp_text)
        painter.setFont(m["f_temp"])
        painter.setPen(primary)
        painter.drawText(
            QRectF(x, 0, temp_w + 2, h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            temp_text,
        )
        x += temp_w + m["gap2"]

        tw = max(20.0, float(r.width()) - x - m["pad"])
        row1, row2 = format_weather_texts(w_tiles)
        fm1, fm2 = QFontMetrics(m["f1"]), QFontMetrics(m["f2"])
        line_gap = max(1.5, 1.8 * bar._scale)
        block_h = fm1.height() + fm2.height() + line_gap
        top = (h - block_h) / 2.0

        painter.setFont(m["f1"])
        painter.setPen(primary)
        painter.drawText(
            QRectF(x, top, tw, fm1.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            fm1.elidedText(row1, Qt.TextElideMode.ElideRight, int(math.ceil(tw))),
        )
        painter.setFont(m["f2"])
        painter.setPen(secondary)
        painter.drawText(
            QRectF(x, top + fm1.height() + line_gap, tw, fm2.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            fm2.elidedText(row2, Qt.TextElideMode.ElideRight, int(math.ceil(tw))),
        )
