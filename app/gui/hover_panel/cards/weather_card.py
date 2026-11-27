"""app/gui/hover_panel/cards/weather_card.py — 实时天气氛围卡片（含逐小时/逐日预报与温标条）"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.core.sources.weather_source import temp_to_color
from app.gui.widgets import motion
from app.styles import icons, tokens
from app.styles.weather_glyph import kind_from_emoji, paint_weather_glyph

from ..primitives import FrostedGlassTile, HoverPill, make_label, make_transparent_widget, ui_font
from .base import BasePanelCard, PanelCardContext


def weather_atmosphere_palette(kind: str, is_day: bool, dark: bool = True) -> tuple[str, str, str, str]:
    """根据天气种类、昼夜与系统主题返回协调的天空氛围渐变 (top, mid, bottom, mode)。"""
    k = str(kind or "partly").lower()
    if k == "sun" and not is_day:
        k = "moon"
    elif k == "partly" and not is_day:
        k = "partly_night"

    if not dark:
        light_map = {
            "moon": ("#E8EEFA", "#F3F6FD", "#FFFFFF", "stars"),
            "partly_night": ("#EBF0F9", "#F5F7FC", "#FFFFFF", "stars_cloud"),
            "sun": ("#E9F4FF", "#F5FAFF", "#FFFFFF", "sunbeams"),
            "partly": ("#EDF4FC", "#F6F9FE", "#FFFFFF", "clouds"),
            "cloud": ("#EEF2F7", "#F7F9FC", "#FFFFFF", "clouds"),
            "rain": ("#E8F0F8", "#F3F7FC", "#FFFFFF", "rain"),
            "shower": ("#E8F0F8", "#F3F7FC", "#FFFFFF", "rain"),
            "thunder": ("#E8EDF6", "#F2F5FA", "#FFFFFF", "thunder"),
            "snow": ("#EDF6FC", "#F7FBFE", "#FFFFFF", "snow"),
            "fog": ("#EEF1F5", "#F7F9FB", "#FFFFFF", "fog"),
        }
        return light_map.get(k, ("#EDF4FC", "#F6F9FE", "#FFFFFF", "clouds"))

    dark_map = {
        "moon": ("#171E33", "#1A2133", "#1B1F29", "stars"),
        "partly_night": ("#182032", "#1B2231", "#1B1F29", "stars_cloud"),
        "sun": ("#18283F", "#1B283A", "#1C212C", "sunbeams"),
        "partly": ("#1A2639", "#1C2534", "#1C202A", "clouds"),
        "cloud": ("#1E2532", "#1D232E", "#1B1F28", "clouds"),
        "rain": ("#182332", "#1B2330", "#1B1F28", "rain"),
        "shower": ("#182332", "#1B2330", "#1B1F28", "rain"),
        "thunder": ("#1A1F30", "#1C212F", "#1B1E27", "thunder"),
        "snow": ("#1D2838", "#1E2633", "#1C2029", "snow"),
        "fog": ("#20252F", "#1E222B", "#1B1F27", "fog"),
    }
    return dark_map.get(k, ("#1A2639", "#1C2534", "#1C202A", "clouds"))


class WeatherGlyphWidget(QWidget):
    """矢量天气图标小部件（仅可见时运行局部微动效）。"""

    def __init__(self, kind: str, dark: bool, is_day: bool, size: int,
                 animated: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._kind = kind
        self._dark = dark
        self._is_day = is_day
        self._animated = animated
        self._phase = 0.0
        self.setFixedSize(size, size)

        self._timer: QTimer | None = None
        if self._animated:
            self._timer = QTimer(self)
            self._timer.setInterval(50)
            self._timer.timeout.connect(self._on_tick)
            if self.isVisible():
                self._timer.start()

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

    def _on_tick(self):
        if not self.isVisible() or self.parent() is None:
            if self._timer is not None and self._timer.isActive():
                self._timer.stop()
            return
        self._phase = (self._phase + 0.018) % 1.0
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        paint_weather_glyph(
            p, QRectF(self.rect()), self._kind, self._dark, self._is_day,
            phase=self._phase if self._animated else 0.0,
        )
        p.end()


class TempRangeBar(QWidget):
    """iOS 扁平拟真温度区间条：内凹轨道 + 顶光立体温标胶囊 + 今日当前温度白珠 + 入场展开动画。"""

    def __init__(self, lo: float, hi: float, gmin: float, gmax: float,
                 dark: bool, height: int, parent: QWidget | None = None,
                 on_sky: bool = False, current_temp: float | None = None):
        super().__init__(parent)
        self._lo, self._hi, self._gmin, self._gmax = lo, hi, gmin, gmax
        self._dark = dark
        self._on_sky = bool(on_sky)
        self._current_temp = current_temp
        self._reveal = motion.ValueTween(1.0, 480, QEasingCurve.Type.OutQuint, parent=self)
        self._reveal.changed.connect(lambda _v: self.update())
        self._delay_timer = QTimer(self)
        self._delay_timer.setSingleShot(True)
        self._delay_timer.timeout.connect(self._run_entrance)
        self.setFixedHeight(max(6, int(height) + 2))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def play_entrance(self, delay_ms: int = 0) -> None:
        self._delay_timer.stop()
        self._reveal.set_immediate(0.0)
        if delay_ms > 0:
            self._delay_timer.start(int(delay_ms))
        else:
            self._run_entrance()

    def stop_entrance(self) -> None:
        self._delay_timer.stop()
        self._reveal.stop()

    def _run_entrance(self) -> None:
        if not self.isVisible():
            return
        self._reveal.animate_to(1.0, duration=480, easing=QEasingCurve.Type.OutQuint, animate=True)

    def hideEvent(self, event):
        self.stop_entrance()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.stop_entrance()
        super().closeEvent(event)

    def paintEvent(self, _e):
        t = tokens.get_tokens(self._dark)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar_h = max(4.0, float(self.height()) - 2.0)
        y = (float(self.height()) - bar_h) / 2.0
        r = QRectF(0.0, y, float(self.width()), bar_h)
        rad = bar_h / 2.0

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(10, 22, 48, 72) if self._on_sky else QColor(*t.track_alpha))
        p.drawRoundedRect(r, rad, rad)
        if self._on_sky:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 36), 0.7))
            p.drawRoundedRect(r.adjusted(0.35, 0.35, -0.35, -0.35), max(1.0, rad - 0.35), max(1.0, rad - 0.35))

        span = max(1.0, self._gmax - self._gmin)
        x1 = r.width() * (self._lo - self._gmin) / span
        x2 = r.width() * (self._hi - self._gmin) / span
        if x2 - x1 < bar_h:
            mid = (x1 + x2) / 2.0
            x1, x2 = mid - rad, mid + rad

        rev = max(0.0, min(1.0, self._reveal.value))
        if rev > 0.01:
            cx = (x1 + x2) / 2.0
            half_w = max(rad, ((x2 - x1) / 2.0) * rev)
            dx1, dx2 = cx - half_w, cx + half_w
            pill = QRectF(dx1, y, dx2 - dx1, bar_h)

            g = QLinearGradient(x1, y, x2, y)
            g.setColorAt(0.0, QColor(temp_to_color(self._lo)))
            g.setColorAt(1.0, QColor(temp_to_color(self._hi)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawRoundedRect(pill, rad, rad)

            hl_h = max(1.2, bar_h * 0.44)
            hl = QLinearGradient(0.0, y, 0.0, y + hl_h)
            hl.setColorAt(0.0, QColor(255, 255, 255, 135))
            hl.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(hl)
            p.drawRoundedRect(
                QRectF(dx1 + 0.6, y + 0.3, max(1.0, dx2 - dx1 - 1.2), hl_h), hl_h / 2.0, hl_h / 2.0
            )

            if self._current_temp is not None and rev > 0.72:
                dot_x = r.width() * (max(self._lo, min(self._hi, float(self._current_temp))) - self._gmin) / span
                dot_x = max(rad + 1.0, min(r.width() - rad - 1.0, dot_x))
                dot_r = bar_h * 0.56
                dot_y = y + bar_h / 2.0
                p.setBrush(QColor(15, 23, 42, 95 if self._on_sky else 65))
                p.drawEllipse(QPointF(dot_x, dot_y + 0.5), dot_r + 0.75, dot_r + 0.75)
                p.setBrush(QColor("#FFFFFF"))
                p.drawEllipse(QPointF(dot_x, dot_y), dot_r, dot_r)
        p.end()


class WeatherAtmosphereCard(QFrame):
    """自适应深浅色的 Liquid Fluent 天气氛围卡片：QPixmap 底图缓存 + 局部微粒子（隐藏停表 0fps）。"""

    _TOP_BAND_MODES = frozenset({"stars", "stars_cloud", "sunbeams", "clouds", "fog"})

    def __init__(self, kind: str, is_day: bool, scale: float,
                 parent: QWidget | None = None, dark: bool = True):
        super().__init__(parent)
        self._kind = str(kind or "partly")
        self._is_day = bool(is_day)
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self._top_c, self._mid_c, self._bot_c, self._mode = weather_atmosphere_palette(
            self._kind, self._is_day, dark=self._dark
        )
        self._phase = 0.0
        self._t0 = time.monotonic()
        self._sky_cache: QPixmap | None = None
        self._sky_cache_size: tuple[int, int] = (0, 0)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        if not self.isVisible() or self.parent() is None:
            self._timer.stop()
            return
        self._phase = (time.monotonic() - self._t0) * 0.22
        if self._mode in self._TOP_BAND_MODES:
            band_h = max(1, int(math.ceil(self.height() * 0.34)))
            self.update(0, 0, self.width(), band_h)
        else:
            self.update()

    def _ensure_sky_cache(self) -> QPixmap | None:
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return None
        if self._sky_cache is not None and self._sky_cache_size == (w, h):
            return self._sky_cache

        t_tok = tokens.get_tokens(self._dark)
        rad = float(tokens.spx(tokens.RADIUS["card"], self._scale, lo=6))
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(*t_tok.shadow_ambient))
        p.drawRoundedRect(QRectF(0.0, 0.0, w, h).adjusted(0.6, 2.2, -0.6, 0.2), rad, rad)
        p.setBrush(QColor(0, 0, 0, 26 if self._dark else 13))
        p.drawRoundedRect(QRectF(0.0, 0.0, w, h).adjusted(0.8, 1.1, -0.8, -0.2), rad, rad)

        r = QRectF(0.0, 0.0, w, h).adjusted(0.6, 0.6, -0.6, -1.4)
        sky = QLinearGradient(r.left(), r.top(), r.left() + r.width() * 0.14, r.bottom())
        sky.setColorAt(0.0, QColor(self._top_c))
        sky.setColorAt(0.38, QColor(self._mid_c))
        sky.setColorAt(1.0, QColor(self._bot_c))
        p.setBrush(sky)
        p.setPen(QPen(QColor(t_tok.border), 1.0))
        p.drawRoundedRect(r, rad, rad)

        p.setBrush(Qt.BrushStyle.NoBrush)
        rim = QLinearGradient(0.0, r.top(), 0.0, r.bottom())
        rim.setColorAt(0.0, QColor(*t_tok.rim_top))
        rim.setColorAt(0.45, QColor(*t_tok.rim_mid))
        rim.setColorAt(1.0, QColor(*t_tok.rim_bottom))
        p.setPen(QPen(rim, 1.0))
        p.drawRoundedRect(r.adjusted(0.8, 0.8, -0.8, -0.8), max(3.0, rad - 0.8), max(3.0, rad - 0.8))
        p.end()

        self._sky_cache = pm
        self._sky_cache_size = (w, h)
        return pm

    def showEvent(self, event):
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event):
        if self._timer.isActive():
            self._timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        if self._timer.isActive():
            self._timer.stop()
        self._sky_cache = None
        self._sky_cache_size = (0, 0)
        super().closeEvent(event)

    def paintEvent(self, event):
        pm = self._ensure_sky_cache()
        if pm is None:
            return
        dirty = event.rect()
        rad = float(tokens.spx(tokens.RADIUS["card"], self._scale, lo=6))
        r = QRectF(self.rect()).adjusted(0.6, 0.6, -0.6, -1.4)

        p = QPainter(self)
        p.drawPixmap(dirty, pm, dirty)

        if self._mode in self._TOP_BAND_MODES and dirty.top() > int(r.height() * 0.35):
            p.end()
            return

        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        clip = QPainterPath()
        clip.addRoundedRect(r, rad, rad)
        p.setClipPath(clip)
        t = self._phase
        w, h = r.width(), r.height()
        band_h = h * 0.34
        p.setPen(Qt.PenStyle.NoPen)

        def _paint_soft_glow(cx: float, cy: float, rx: float, ry: float, stops) -> None:
            if rx <= 1.0 or ry <= 1.0:
                return
            p.save()
            p.translate(cx, cy)
            p.scale(1.0, ry / rx)
            g = QRadialGradient(0.0, 0.0, rx)
            for pos, col in stops:
                g.setColorAt(pos, col)
            p.setBrush(g)
            p.drawEllipse(QPointF(0.0, 0.0), rx, rx)
            p.restore()

        if self._mode in ("stars", "stars_cloud"):
            glow_x = r.left() + w * (0.19 + 0.015 * math.sin(t * 1.4))
            glow_y = r.top() + min(band_h * 0.44, 72.0 * self._scale)
            rx = max(w * 0.42, 130.0 * self._scale)
            ry = max(24.0, band_h - (glow_y - r.top()) - 2.0)
            pulse = 0.5 + 0.5 * math.sin(t * 1.8)
            if self._dark:
                stops = (
                    (0.0, QColor(199, 210, 254, int(42 + 18 * pulse))),
                    (0.55, QColor(129, 140, 248, int(16 + 8 * pulse))),
                    (1.0, QColor(99, 102, 241, 0)),
                )
            else:
                stops = (
                    (0.0, QColor(99, 102, 241, int(30 + 14 * pulse))),
                    (0.55, QColor(129, 140, 248, int(11 + 6 * pulse))),
                    (1.0, QColor(99, 102, 241, 0)),
                )
            _paint_soft_glow(glow_x, glow_y, rx, ry, stops)

            for i in range(10):
                fx = ((i * 73 + 19) % 90 + 5) / 100.0
                fy = ((i * 37 + 7) % 16 + 3) / 100.0
                sx = r.left() + w * fx
                sy = r.top() + h * fy
                tw = 0.28 + 0.72 * (0.5 + 0.5 * math.sin(t * (2.6 + (i % 4) * 0.7) + i * 1.7))
                sr = (0.9 + (i % 3) * 0.35) * self._scale * (0.75 + 0.32 * tw)
                star_c = QColor(224, 231, 255, int(160 * tw)) if self._dark else QColor(99, 102, 241, int(105 * tw))
                p.setBrush(star_c)
                p.drawEllipse(QPointF(sx, sy), sr, sr)

        elif self._mode == "sunbeams":
            pulse = 0.5 + 0.5 * math.sin(t * 1.6)
            sx = r.right() - w * 0.14
            sy = r.top() + min(band_h * 0.28, 48.0 * self._scale)
            rx = max(w * 0.56, 155.0 * self._scale)
            ry = max(28.0, band_h - (sy - r.top()) - 2.0)
            if self._dark:
                stops = (
                    (0.0, QColor(255, 224, 130, int(48 + 18 * pulse))),
                    (0.52, QColor(251, 191, 36, int(16 + 8 * pulse))),
                    (1.0, QColor(255, 255, 255, 0)),
                )
            else:
                stops = (
                    (0.0, QColor(253, 224, 71, int(52 + 18 * pulse))),
                    (0.52, QColor(251, 191, 36, int(18 + 8 * pulse))),
                    (1.0, QColor(255, 255, 255, 0)),
                )
            _paint_soft_glow(sx, sy, rx, ry, stops)

        if self._mode in ("clouds", "stars_cloud", "fog"):
            c_rgb = (255, 255, 255) if self._dark else (148, 163, 184)
            for idx, (base_y, amp_x, spd, alpha) in enumerate(((0.10, 0.14, 0.45, 26), (0.19, 0.18, -0.32, 18))):
                cx = r.left() + w * (0.5 + amp_x * math.sin(t * spd + idx * 2.1))
                cy = r.top() + h * base_y
                ry = max(14.0, min(h * 0.09, band_h - (cy - r.top()) - 2.0))
                _paint_soft_glow(
                    cx, cy, w * 0.46, ry, ((0.0, QColor(*c_rgb, alpha)), (1.0, QColor(*c_rgb, 0)))
                )

        elif self._mode in ("rain", "thunder"):
            rain_c = QColor(186, 230, 253, 52) if self._dark else QColor(59, 130, 246, 46)
            pen = QPen(rain_c, max(1.0, 1.1 * self._scale))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            for i in range(16):
                fx = ((i * 59 + 13) % 98) / 100.0
                prog = (t * (2.6 + (i % 3) * 0.5) + i * 0.23) % 1.0
                rx = r.left() + w * fx - prog * 18.0 * self._scale
                ry = r.top() + h * prog
                ln = (12.0 + (i % 3) * 5.0) * self._scale
                p.drawLine(QPointF(rx, ry), QPointF(rx - ln * 0.22, ry + ln))

        elif self._mode == "snow":
            for i in range(14):
                fx = ((i * 67 + 17) % 96 + 2) / 100.0
                prog = (t * (0.75 + (i % 3) * 0.2) + i * 0.19) % 1.0
                sx = r.left() + w * fx + math.sin(t * 2.5 + i * 1.4) * 9.0 * self._scale
                sy = r.top() + h * prog
                sr = (1.5 + (i % 3) * 0.65) * self._scale
                a = int((125 + 55 * math.sin(prog * math.pi)) if self._dark else (85 + 45 * math.sin(prog * math.pi)))
                p.setBrush(QColor(255, 255, 255, a) if self._dark else QColor(56, 189, 248, a))
                p.drawEllipse(QPointF(sx, sy), sr, sr)

        p.end()


class WeatherPanelCard(BasePanelCard):
    """天气氛围卡片控制器：封装逐小时/逐日预报、气象雷达入口与温标条错峰动画。"""

    card_id = "weather"
    source_ids = ("weather",)

    def __init__(self) -> None:
        self.card: WeatherAtmosphereCard | None = None
        self.boxes: dict[str, QLabel] = {}
        self.temp_range_bars: list[TempRangeBar] = []

    def reset(self) -> None:
        self.card = None
        self.boxes = {}
        self.temp_range_bars = []

    def build(self, ctx: PanelCardContext) -> QWidget | None:
        src_cfg = ctx.cfg.get("sources") or {}
        if not src_cfg.get("weather", {}).get("enabled", True):
            return None
        w_tiles = ctx.source_tiles.get("weather")
        if not w_tiles:
            return None

        dark, scale = ctx.dark, ctx.scale
        sp = lambda v, lo=1: tokens.spx(v, scale, lo=lo)

        t0 = w_tiles[0]
        winfo = t0.get("weather_info") or {}
        city_name = winfo.get("city") or t0.get("name") or "当地"
        kind = winfo.get("kind") or kind_from_emoji(str(winfo.get("icon") or ""))
        is_day = bool(winfo.get("is_day", True))
        temp_str = str(t0.get("center_text") or "--°")
        cur_temp_val = winfo.get("temp_c")
        cond_str = str(winfo.get("condition") or t0.get("sub_text") or "")
        feels = winfo.get("feels_like_c")
        max_t, min_t = winfo.get("max_temp_c"), winfo.get("min_temp_c")

        t = tokens.get_tokens(dark)
        sky_fg, sky_sub, sky_muted = t.text, t.text_secondary, t.text_muted
        sky_accent = t.info if dark else t.accent
        accent_role = "info" if dark else "accent"

        def make_glass_box(name: str = "", interactive: bool = False) -> tuple[FrostedGlassTile, QVBoxLayout]:
            box = FrostedGlassTile(scale, interactive=interactive, dark=dark)
            if name:
                box.setObjectName(name)
            bv = QVBoxLayout(box)
            bv.setContentsMargins(sp(11, 7), sp(8, 5), sp(11, 7), sp(8, 5))
            bv.setSpacing(sp(6, 3))
            return box, bv

        card = WeatherAtmosphereCard(kind, is_day, scale, dark=dark)
        v = QVBoxLayout(card)
        v.setContentsMargins(sp(14, 10), sp(11, 7), sp(14, 10), sp(11, 7))
        v.setSpacing(sp(8, 5))

        head = make_transparent_widget()
        hh_top = QHBoxLayout(head)
        hh_top.setContentsMargins(sp(2), 0, sp(2), 0)
        hh_top.setSpacing(sp(7))
        hh_top.addWidget(icons.IconWidget("weather", sky_accent, size=sp(15)), 0, Qt.AlignmentFlag.AlignVCenter)
        hh_top.addWidget(make_label("实时天气", 13 * scale, sky_fg, 700, role="primary"), 0, Qt.AlignmentFlag.AlignVCenter)
        hh_top.addStretch(1)
        city_lbl = QLabel(f"📍 {city_name}")
        city_lbl.setObjectName("weatherCityBadge")
        city_lbl.setFont(ui_font(11 * scale, 600))
        city_lbl.setFixedHeight(max(22, sp(22)))
        city_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hh_top.addWidget(city_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        v.addWidget(head)

        main = make_transparent_widget()
        mh = QHBoxLayout(main)
        mh.setContentsMargins(sp(4, 2), sp(2, 1), sp(4, 2), sp(2, 1))
        mh.setSpacing(sp(12, 6))
        mh.addWidget(WeatherGlyphWidget(kind, dark, is_day, sp(54, 36), animated=True), 0, Qt.AlignmentFlag.AlignVCenter)
        temp_lbl = make_label(temp_str, 32 * scale, sky_fg, 600, role="primary")
        mh.addWidget(temp_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        mv = QVBoxLayout()
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(sp(2, 1))
        cond_s = cond_str + (f" · 体感 {int(round(feels))}°" if feels is not None else "")
        cond_lbl = make_label(cond_s, 12.5 * scale, sky_fg, 600, role="primary")
        mv.addWidget(cond_lbl)
        range_lbl = make_label(
            f"最高 {int(round(max_t))}°   最低 {int(round(min_t))}°"
            if max_t is not None and min_t is not None else "",
            11 * scale, sky_sub, 500, mono=True, role="secondary",
        )
        mv.addWidget(range_lbl)
        mh.addLayout(mv, 1)
        v.addWidget(main)

        hourly = [x for x in (winfo.get("hourly") or []) if isinstance(x, dict)]
        if hourly:
            box, bv = make_glass_box("wxHourly", interactive=False)
            bv.addWidget(make_label("未来 24 小时", 10.5 * scale, sky_muted, 600, role="muted"))
            strip = QHBoxLayout()
            strip.setContentsMargins(0, 0, 0, 0)
            strip.setSpacing(sp(2, 1))
            for i, item in enumerate(hourly[:8]):
                pill = HoverPill(scale, active=(i == 0), radius=7.0, dark=dark)
                col = QVBoxLayout(pill)
                col.setContentsMargins(sp(2, 1), sp(5, 3), sp(2, 1), sp(5, 3))
                col.setSpacing(sp(3, 2))
                hh = str(item.get("time", ""))[:2].lstrip("0") or "0"
                t_col = sky_accent if (i == 0 and not dark) else (sky_fg if i == 0 else sky_muted)
                t_role = accent_role if (i == 0 and not dark) else ("primary" if i == 0 else "muted")
                tl = make_label("现在" if i == 0 else f"{hh}时", 10 * scale, t_col, 700 if i == 0 else 500, role=t_role)
                tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                col.addWidget(tl)
                slot_kind = kind if i == 0 else item.get("kind", "partly")
                slot_is_day = is_day if i == 0 else bool(item.get("is_day", True))
                slot_temp = cur_temp_val if (i == 0 and cur_temp_val is not None) else item.get("temp", 0)
                col.addWidget(WeatherGlyphWidget(slot_kind, dark, slot_is_day, sp(23, 16)), 0, Qt.AlignmentFlag.AlignHCenter)
                vl = make_label(f"{int(round(slot_temp))}°", 11.5 * scale, sky_fg, 600, mono=True, role="primary")
                vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                col.addWidget(vl)
                strip.addWidget(pill, 1)
            bv.addLayout(strip)
            v.addWidget(box)

        daily = [x for x in (winfo.get("daily") or []) if isinstance(x, dict)]
        if daily:
            box, bv = make_glass_box("wxDaily", interactive=True)
            box.setToolTip("点击在浏览器中打开气象雷达与逐小时降水动态图")
            radar_url = winfo.get("radar_url") or "https://www.windy.com/?radar"
            box.clicked.connect(lambda u=radar_url: QDesktopServices.openUrl(QUrl(u)))

            hdr = make_transparent_widget()
            hh = QHBoxLayout(hdr)
            hh.setContentsMargins(0, 0, 0, 0)
            hh.setSpacing(sp(5, 3))
            hh.addWidget(make_label(f"{len(daily)} 天预报", 10.5 * scale, sky_muted, 600, role="muted"), 0)
            hh.addStretch(1)
            hh.addWidget(icons.IconWidget("radar", sky_accent, size=sp(12, 10)), 0, Qt.AlignmentFlag.AlignVCenter)
            hh.addWidget(make_label("气象雷达 ↗", 10.5 * scale, sky_accent, 600, role=accent_role), 0)
            bv.addWidget(hdr)

            gmin = min(float(d["min"]) for d in daily)
            gmax = max(float(d["max"]) for d in daily)
            for idx_d, d in enumerate(daily):
                row = HoverPill(scale, active=False, radius=6.0, dark=dark)
                rh = QHBoxLayout(row)
                rh.setContentsMargins(sp(4, 2), sp(2, 1), sp(4, 2), sp(2, 1))
                rh.setSpacing(sp(7, 4))
                day_lbl = make_label(str(d.get("label", "")), 11.5 * scale, sky_fg, 600, role="primary")
                day_lbl.setFixedWidth(sp(38, 28))
                rh.addWidget(day_lbl)
                rh.addWidget(WeatherGlyphWidget(d.get("kind", "partly"), dark, True, sp(21, 15)))
                pop = d.get("pop")
                pop_lbl = make_label(
                    f"{pop}%" if pop is not None and pop >= 20 else "",
                    9.5 * scale, sky_accent, 700, mono=True, role=accent_role,
                )
                pop_lbl.setFixedWidth(sp(30, 22))
                pop_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                rh.addWidget(pop_lbl)
                lo_lbl = make_label(f"{int(round(d['min']))}°", 11.5 * scale, sky_muted, 500, mono=True, role="muted")
                lo_lbl.setFixedWidth(sp(28, 20))
                lo_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                rh.addWidget(lo_lbl)
                tbar = TempRangeBar(
                    float(d["min"]), float(d["max"]), gmin, gmax, dark, sp(6, 5),
                    on_sky=dark, current_temp=cur_temp_val if idx_d == 0 else None,
                )
                self.temp_range_bars.append(tbar)
                rh.addWidget(tbar, 1, Qt.AlignmentFlag.AlignVCenter)
                hi_lbl = make_label(f"{int(round(d['max']))}°", 11.5 * scale, sky_fg, 600, mono=True, role="primary")
                hi_lbl.setFixedWidth(sp(28, 20))
                rh.addWidget(hi_lbl)
                bv.addWidget(row)
            v.addWidget(box)

        row = make_transparent_widget()
        rh = QHBoxLayout(row)
        rh.setContentsMargins(0, 0, 0, 0)
        rh.setSpacing(sp(8, 6))

        self.card = card
        self.boxes = {"city": city_lbl, "temp": temp_lbl, "cond": cond_lbl, "range": range_lbl}
        for mt in w_tiles[1:]:
            box, bv = make_glass_box("wxMetric_" + str(mt.get("id", "")).replace(":", "_"), interactive=False)
            top_h = QHBoxLayout()
            top_h.setContentsMargins(0, 0, 0, 0)
            top_h.addWidget(make_label(mt.get("name", ""), 11 * scale, sky_muted, 600, role="muted"), 0)
            top_h.addStretch(1)
            top_h.addWidget(make_label(mt.get("center_text", ""), 12.5 * scale, sky_fg, 700, mono=True, role="primary"), 0)
            bv.addLayout(top_h)
            bv.addWidget(make_label(mt.get("sub_text", ""), 10.5 * scale, sky_sub, 500, role="secondary"))
            rh.addWidget(box, 1)
        v.addWidget(row)
        return card

    def play_entrance(self) -> None:
        for idx, tbar in enumerate(self.temp_range_bars):
            tbar.play_entrance(delay_ms=70 + idx * 45)

    def stop_animations(self) -> None:
        for tbar in self.temp_range_bars:
            tbar.stop_entrance()
