"""app/gui/taskbar/widget.py — 任务栏常驻条核心控件（状态机 + 动画驱动 + 视图策略委托）"""

from __future__ import annotations

import datetime
import logging
import math
import os
import time

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from app.core import config as config_mod
from app.core import tiles
from app.core.logger import get_logger
from app.gui.widgets import motion
from app.platform import win32_utils
from app.styles import theme, tokens

from .menu_builder import BarContextMenuBuilder, compute_menu_popup_pos, resolve_menu_popup_pos
from .views import (
    VIEW_LABELS,
    VIEW_QUOTA,
    VIEW_SCHEDULE,
    VIEW_SYSTEM,
    VIEW_WEATHER,
    BarViewRegistry,
    build_default_view_registry,
)
from .views.capsule_view import CapsuleViewRenderer
from .views.schedule_view import paint_focus_ring, paint_scrolling_row2, paint_spectrum
from .views.shared_painters import (
    build_bar_fonts,
    optical_line_height,
    paint_liquid_glass_island,
    preferred_families,
    schedule_ring_geometry,
    telemetry_fonts,
)
from .views.tiles_view import compute_tiles_layout, tile_display_value
from .views.weather_view import format_weather_texts, weather_metrics, weather_temp_text

TICK_MS = 25  # 40 FPS，兼顾小字号跑马灯丝滑度与能耗
SCROLL_SEP = "   \u00b7   "
FADE_PX = 16.0
HOVER_FADE_MS = float(tokens.MOTION["fast"])
VIEW_TRANSITION_SEC = tokens.MOTION["standard"] / 1000.0
RING_SMOOTH_RATE = 11.0
ICON_SLOT_LOGICAL = 20
ICON_GAP_LOGICAL = 5
DOT_LOGICAL = 6.0
DOT_GAP_LOGICAL = 7.0

_TICK_DEBUG_TAGS = {"tick", "swp_pre", "swp_post", "paint"}
_tick_logger = get_logger("anybar.tick", "tick.log", env_var="TOUCHBAR_TICK_LOG")


def _tick_log(tag, **kw):
    is_debug = tag in _TICK_DEBUG_TAGS
    if is_debug:
        if not _tick_logger.isEnabledFor(logging.DEBUG):
            return
    elif not _tick_logger.isEnabledFor(logging.INFO):
        return
    parts = [tag]
    for k, v in kw.items():
        parts.append(f"{k}={v}")
    msg = " ".join(str(p) for p in parts)
    if is_debug:
        _tick_logger.debug(msg)
    else:
        _tick_logger.info(msg)


class BarWidget(QWidget):
    """任务栏常驻自绘控件：管理状态、帧调度与 DWM 防冻结，渲染全部委托给视图策略注册表。"""

    request_settings = Signal()
    request_quit = Signal()
    request_edit_todos = Signal()
    request_refresh = Signal()
    menu_about_to_show = Signal()
    menu_closed = Signal()
    paint_stalled = Signal()
    content_width_changed = Signal(int)
    theme_mode_changed = Signal(str)

    def __init__(self, cfg: dict, parent=None, view_registry: BarViewRegistry | None = None):
        super().__init__(parent)
        self._cfg = cfg
        self._view_registry = view_registry or build_default_view_registry()
        self._capsule_renderer = CapsuleViewRenderer()

        self._paused = False
        self._hover = False
        self._hover_progress = 0.0
        self._compact = False
        self._capsule_collapsed = cfg.get("style", {}).get("displayMode") == "capsule"
        self._offset = 0.0
        self._last_ts = None
        self._rest_until = 0.0
        self._focus_until = 0.0
        self._focus_total = 1800.0
        self._glow_active = False
        self._glow_phase = 0.0
        self._glow_last_ts = None
        self._font = QFont()
        self._font_row1 = QFont()
        self._font_row2 = QFont()
        self._font_quota_name = QFont()
        self._font_quota_val = QFont()
        self._row1_color = QColor("#FFFFFF")
        self._row2_color = QColor("#38BDF8")
        self._dot_color = QColor("#F59E0B")
        self._row1 = ""
        self._row2 = ""
        self._speed = 30.0
        self._tb_color = None
        self._fade_px = FADE_PX
        self._scale = 1.0
        self._row2_pm = None
        self._row2_pm_key = None
        self._update_cached_text_widths()
        self._last_view_toggle = 0.0
        self._view_anim_progress = 1.0
        self._hover_sheen = 2.0
        self._urgent_pulse_ts = 0.0
        self._urgent_pulse_until = 0.0
        self._cached_has_urgent = None
        self._weather_phase = 0.0
        self._ring_display: dict[str, float] = {}
        self._ring_targets: dict[str, float] = {}
        self._quota_state = None
        self._source_tiles: dict[str, list[dict]] = {}

        self._cached_row1_w = 0
        self._cached_row2_w = 0
        self._cached_avail = 20
        self._cached_avail_sig = None
        self._cached_available_views = None
        self._cached_current_view = None

        self._gap = 90.0
        self._rest_sec = 8.0
        self._last_paint_mono = time.monotonic()
        self._paint_stall = 0
        self._paint_stall_fails = 0

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(TICK_MS)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

        self._minute_timer = QTimer(self)
        self._minute_timer.setInterval(30 * 1000)
        self._minute_timer.timeout.connect(self.refresh_content)
        self._minute_timer.start()

        self._focus_timer = QTimer(self)
        self._focus_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._focus_timer.setInterval(250)
        self._focus_timer.timeout.connect(self._on_focus_tick)

        self._glow_timer = QTimer(self)
        self._glow_timer.setInterval(33)
        self._glow_timer.timeout.connect(self._on_glow_tick)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

        self.apply_style()
        self.refresh_content()

    # ── 状态与数据源注入 ──────────────────────────────────────────────────────

    def _update_cached_text_widths(self) -> None:
        self._cached_row1_w = self._text_width_row1(self._sizing_row1())
        self._cached_row2_w = self._text_width(self._row2)

    def _invalidate_view_cache(self) -> None:
        self._cached_available_views = None
        self._cached_current_view = None
        self._cached_has_urgent = None

    def _has_urgent_quota(self) -> bool:
        if self._cached_has_urgent is None:
            if self.is_quota_view():
                self._cached_has_urgent = any(
                    float(q.get("ratio") if q.get("ratio") is not None else q.get("frac", 1.0)) <= 0.20
                    for q in self.current_tiles()
                )
            else:
                self._cached_has_urgent = False
        return bool(self._cached_has_urgent)

    def set_config(self, cfg: dict) -> None:
        self._invalidate_view_cache()
        self._cfg = cfg
        self.apply_style()
        self.refresh_content()

    def set_quota_state(self, state) -> None:
        self._invalidate_view_cache()
        self._quota_state = state
        self._urgent_pulse_until = time.monotonic() + 3.0
        self.refresh_content()

    def set_source_tiles(self, source_id: str, tile_list: list[dict]) -> None:
        self._invalidate_view_cache()
        self._source_tiles[source_id] = list(tile_list or [])
        if self.is_tiles_view() or self.is_weather_view():
            self.refresh_content()
            self.content_width_changed.emit(self.desired_width())

    def set_taskbar_color(self, rgb) -> None:
        if rgb and rgb != self._tb_color:
            self._tb_color = rgb
            self.update()

    def set_hover(self, h: bool) -> None:
        if h != self._hover:
            self._hover = h
            if h:
                self._hover_sheen = -0.35
            self.update()

    def is_capsule_mode(self) -> bool:
        return self._cfg.get("style", {}).get("displayMode") == "capsule"

    def set_compact(self, c: bool) -> None:
        if c != self._compact:
            self._compact = c
            self.update()

    def set_capsule_collapsed(self, collapsed: bool) -> None:
        if getattr(self, "_capsule_collapsed", False) != bool(collapsed):
            self._capsule_collapsed = bool(collapsed)
            self._view_anim_progress = 0.0
            self.update()
            self._swp_frame(time.monotonic())
            self.content_width_changed.emit(self.desired_width())

    def suspend_animations(self) -> None:
        if self._tick_timer.isActive():
            self._tick_timer.stop()
        if self._glow_timer.isActive():
            self._glow_timer.stop()

    def resume_animations(self) -> None:
        self._last_ts = None
        self._last_paint_mono = time.monotonic()
        self._paint_stall = 0
        self._paint_stall_fails = 0
        if not self._tick_timer.isActive():
            self._tick_timer.start()
        self._update_glow()
        self.update()

    def toggle_pause(self) -> bool:
        self._paused = not self._paused
        return self._paused

    def is_paused(self) -> bool:
        return self._paused

    def _on_user_refresh(self) -> None:
        self.refresh_content()
        self.request_refresh.emit()

    def toggle_focus(self, minutes: int = 30) -> None:
        if self._focus_until and time.monotonic() < self._focus_until:
            self._focus_until = 0.0
            self._focus_timer.stop()
        else:
            self._focus_total = max(1.0, float(minutes * 60))
            self._focus_until = time.monotonic() + minutes * 60
            self._focus_timer.start()
        self.refresh_content()

    def _on_focus_tick(self) -> None:
        if self._focus_until and time.monotonic() >= self._focus_until:
            self._focus_until = 0.0
            self._focus_timer.stop()
            self.refresh_content()
            return
        new_row1, new_row2 = self.current_texts()
        if (new_row1, new_row2) == (self._row1, self._row2):
            return
        self._row1, self._row2 = new_row1, new_row2
        self.update()
        self._swp_frame(time.monotonic())

    # ── 样式、字体与排版度量 ──────────────────────────────────────────────────

    def apply_style(self) -> None:
        style = self._cfg["style"]
        scale = win32_utils.get_system_dpi() / 96
        self._scale = scale
        dark = theme.is_system_dark()
        family = style.get("fontFamily", "Microsoft YaHei UI")
        base_px = max(9, round(int(style.get("fontSize", 10)) * scale))
        font1 = QFont()
        font1.setFamilies([family, "Segoe UI Emoji", "Microsoft YaHei UI"])
        font1.setPixelSize(base_px)
        font1.setBold(True)
        font2 = QFont()
        font2.setFamilies([family, "Segoe UI Emoji", "Microsoft YaHei UI"])
        font2.setPixelSize(max(8, base_px - max(1, round(1 * scale))))
        q_px = max(8, base_px - max(1, round(1 * scale)))
        font_qn = QFont()
        font_qn.setFamilies(["Segoe UI Variable Text", "Segoe UI", family, "Microsoft YaHei UI"])
        font_qn.setPixelSize(q_px)
        font_qn.setWeight(QFont.Weight.Medium)
        font_qv = QFont()
        font_qv.setFamilies(["Segoe UI Variable Display", "Segoe UI", family, "Microsoft YaHei UI"])
        font_qv.setPixelSize(q_px)
        font_qv.setWeight(QFont.Weight.Bold)
        self._font = font1
        self._font_row1 = font1
        self._font_row2 = font2
        self._font_quota_name = font_qn
        self._font_quota_val = font_qv
        self._synced_font_sig = None
        self._row2_pm = None
        self._row2_pm_key = None
        self._speed = max(1.0, float(style.get("scrollSpeed", 30))) * scale
        self._gap = max(20.0, float(style.get("gapPx", 90))) * scale
        self._rest_sec = max(0.0, float(style.get("scrollPauseSec", 8)))
        self._fade_px = max(8.0, 14.0 * scale)
        t = tokens.get_tokens(dark)
        if style.get("autoColor", True):
            self._row1_color = QColor(t.text)
            self._row2_color = QColor(t.text_secondary)
        else:
            self._row1_color = QColor(
                style.get("darkThemeColor", t.text) if dark else style.get("lightThemeColor", t.text)
            )
            self._row2_color = QColor(style.get("rightColor", t.text_secondary))
        self._dot_color = QColor(t.warn_solid)
        self._sync_schedule_fonts(self._effective_bar_height())
        self._update_cached_text_widths()
        self._reset_scroll()
        self.update()
        self.content_width_changed.emit(self.desired_width())

    def _effective_bar_height(self) -> int:
        max_bar_h = int(96 * self._scale)
        h = self.height()
        return h if 20 <= h <= max_bar_h else int(44 * self._scale)

    def _preferred_families(self, display: bool = False) -> list[str]:
        return preferred_families(self._cfg["style"], display=display)

    def _build_bar_fonts(self, h: float):
        return build_bar_fonts(self._cfg["style"], self._scale, h)

    @staticmethod
    def _optical_line_height(font: QFont, fm: QFontMetrics) -> float:
        return optical_line_height(font, fm)

    def _schedule_ring_geometry(self, h: float) -> tuple[float, float, float, float]:
        return schedule_ring_geometry(self._scale, h)

    def _telemetry_fonts(self, h: float):
        return telemetry_fonts(self._cfg["style"], self._scale, h)

    def _sync_schedule_fonts(self, h: float) -> None:
        style = self._cfg["style"]
        sig = (
            int(round(h)),
            style.get("fontFamily", "Microsoft YaHei UI"),
            int(style.get("fontSize", 10)),
            bool(style.get("bold", True)),
        )
        if getattr(self, "_synced_font_sig", None) == sig:
            return
        self._synced_font_sig = sig
        f1, f2 = build_bar_fonts(style, self._scale, h)
        self._font = f1
        self._font_row1 = f1
        self._font_row2 = f2
        self._row2_pm = None
        self._row2_pm_key = None

    def _reset_scroll(self) -> None:
        self._offset = 0.0
        self._rest_until = 0.0

    # ── 数据文本与视图路由（委托 BarViewRegistry） ────────────────────────────

    def _weather_texts(self) -> tuple[str, str]:
        return format_weather_texts(self._source_tiles.get("weather") or [])

    def _weather_temp_text(self) -> str:
        return weather_temp_text(self._source_tiles.get("weather") or [])

    def _weather_metrics(self, h: float) -> dict:
        return weather_metrics(self._cfg["style"], self._scale, h)

    def current_texts(self) -> tuple[str, str]:
        if self._focus_until:
            remain = self._focus_until - time.monotonic()
            if remain > 0:
                m = int(remain // 60)
                s = int(remain % 60)
                return f"专注模式 · 剩余 {m}分{s}秒", "保持专注，少看手机"
            self._focus_until = 0.0
            self._focus_timer.stop()
        if self.is_weather_view():
            return self._weather_texts()
        item = config_mod.current_schedule(self._cfg, datetime.datetime.now())
        left = item.get("text", "") if item else self._cfg.get("defaultText", "")
        parts = []
        for t in self._cfg.get("todos", []):
            if t.get("done"):
                continue
            title = t.get("title", "").strip()
            if not title:
                continue
            prefix = f"[{t.get('time', '')}] " if t.get("time") else ""
            parts.append(f"{prefix}{title}")
        right = SCROLL_SEP.join(parts) if parts else "暂无待办 \u00b7 右键打开设置添加"
        return left, right

    def _card_to_bar_item(self, card: dict, hig: dict) -> dict | None:
        return tiles.card_to_tile(card, hig)

    def _auto_quota_items(self) -> list[dict]:
        hig = theme.hig_palette(theme.is_system_dark())
        return tiles.tiles_from_quota_state(self._quota_state, {"quotaApi": self._cfg.get("quotaApi")}, hig, limit=4)

    def _valid_quotas(self) -> list[dict]:
        hig = theme.hig_palette(theme.is_system_dark())
        return tiles.tiles_from_quota_state(self._quota_state, self._cfg, hig, limit=4)

    @staticmethod
    def _fmt_num(v, compact: bool = True) -> str:
        return tiles.fmt_num(v, compact)

    def available_views(self) -> list[str]:
        if getattr(self, "_cached_available_views", None) is not None:
            return self._cached_available_views
        views = self._view_registry.available_views(self)
        self._cached_available_views = views
        return views

    def current_view(self) -> str:
        if getattr(self, "_cached_current_view", None) is not None:
            return self._cached_current_view
        cur = str(self._cfg["style"].get("barView", VIEW_SCHEDULE))
        avail = self.available_views()
        if cur == "tiles":
            cur = VIEW_SYSTEM if VIEW_SYSTEM in avail else (VIEW_QUOTA if VIEW_QUOTA in avail else VIEW_SCHEDULE)
        result = cur if cur in avail else VIEW_SCHEDULE
        self._cached_current_view = result
        return result

    def is_tiles_view(self) -> bool:
        return self.current_view() in (VIEW_SYSTEM, VIEW_QUOTA)

    def is_quota_view(self) -> bool:
        return self.current_view() == VIEW_QUOTA

    def is_system_view(self) -> bool:
        return self.current_view() == VIEW_SYSTEM

    def is_weather_view(self) -> bool:
        return self.current_view() == VIEW_WEATHER

    def current_tiles(self) -> list[dict]:
        mode = self.current_view()
        if mode == VIEW_SYSTEM:
            return list(self._source_tiles.get("system", []))[:3]
        if mode == VIEW_QUOTA:
            return self._valid_quotas()[:4]
        if mode == VIEW_WEATHER:
            return list(self._source_tiles.get("weather", []))[:3]
        return []

    def toggle_view(self, target_view: str | None = None) -> None:
        self._invalidate_view_cache()
        avail = self.available_views()
        if not avail:
            return
        cur = self.current_view()
        if target_view is not None:
            next_view = target_view if target_view in avail else VIEW_SCHEDULE
        else:
            try:
                idx = avail.index(cur)
                next_view = avail[(idx + 1) % len(avail)]
            except ValueError:
                next_view = avail[0]

        self._cfg["style"]["barView"] = next_view
        self._invalidate_view_cache()
        self._view_anim_progress = 0.0
        self._hover_sheen = -0.35
        self._urgent_pulse_until = time.monotonic() + 3.0
        for k in list(self._ring_display.keys()):
            self._ring_display[k] = 0.06
        config_mod.save_config(self._cfg)
        new_w = self.desired_width()
        self.content_width_changed.emit(new_w)
        self.refresh_content()

    @staticmethod
    def _tile_display_value(q: dict, is_sys: bool) -> str:
        return tile_display_value(q, is_sys)

    def _tiles_layout(self, w: int, h: float):
        return compute_tiles_layout(self, w, h)

    def _display_ring_ratio(self, key: str, target: float) -> float:
        tgt = max(0.0, min(1.0, float(target)))
        self._ring_targets[key] = tgt
        if key not in self._ring_display:
            self._ring_display[key] = tgt
            return tgt
        return self._ring_display[key]

    def _sizing_row1(self) -> str:
        if self._focus_until and time.monotonic() < self._focus_until:
            return "专注模式 · 剩余 88分88秒"
        return self._row1

    def desired_width(self) -> int:
        dpr = win32_utils.get_system_dpi() / 96
        if self.is_capsule_mode() and getattr(self, "_capsule_collapsed", False):
            return int(128 * dpr)
        h = float(self._effective_bar_height())
        strat = self._view_registry.get(self.current_view()) or self._view_registry.get(VIEW_SCHEDULE)
        return strat.desired_width(self, h, dpr)

    def refresh_content(self) -> None:
        new_row1, new_row2 = self.current_texts()
        if (new_row1, new_row2) != (self._row1, self._row2):
            self._row1, self._row2 = new_row1, new_row2
            self._update_cached_text_widths()
            self._reset_scroll()
        self._update_glow()
        self.update()
        self._swp_frame(time.monotonic())
        self.content_width_changed.emit(self.desired_width())

    def _update_glow(self) -> None:
        if self._focus_until and time.monotonic() < self._focus_until:
            self._stop_glow()
            return
        now = datetime.datetime.now()
        _, remain = config_mod.next_schedule(self._cfg, now)
        if remain is not None and 0 < remain <= 5:
            self._glow_active = True
            if not self._glow_timer.isActive():
                self._glow_last_ts = None
                self._glow_timer.start()
        else:
            self._stop_glow()

    def _stop_glow(self) -> None:
        self._glow_active = False
        self._glow_timer.stop()

    def _on_glow_tick(self) -> None:
        now = time.monotonic()
        if self._glow_last_ts is None:
            self._glow_last_ts = now
            return
        dt = now - self._glow_last_ts
        self._glow_last_ts = now
        self._glow_phase += 2 * math.pi * dt / 4.0
        self.update()

    def _fm(self) -> QFontMetrics:
        return QFontMetrics(self._font_row2)

    def _fm1(self) -> QFontMetrics:
        return QFontMetrics(self._font_row1)

    def _text_width(self, text: str) -> int:
        return self._fm().horizontalAdvance(text)

    def _text_width_row1(self, text: str) -> int:
        return self._fm1().horizontalAdvance(text)

    # ── 帧循环、DWM 防冻结与看门狗 ────────────────────────────────────────────

    def _tick(self) -> None:
        now = time.monotonic()
        if now - getattr(self, "_tick_log_ts", 0.0) > 2.0:
            self._tick_log_ts = now
            _tick_log(
                "tick", paused=self._paused, offset=round(self._offset, 1),
                rest=bool(self._rest_until), w=self.width(),
                text_w=self._cached_row2_w, row2=self._row2[:30],
            )
        if self._last_ts is None:
            self._last_ts = now
            return
        dt = now - self._last_ts
        self._last_ts = now

        hover_target = 1.0 if self._hover else 0.0
        hover_moving = self._hover_progress != hover_target
        if hover_moving:
            step = dt / (HOVER_FADE_MS / 1000.0)
            if self._hover_progress < hover_target:
                self._hover_progress = min(hover_target, self._hover_progress + step)
            else:
                self._hover_progress = max(hover_target, self._hover_progress - step)
            hover_moving = self._hover_progress != hover_target

        animating = hover_moving

        if self._view_anim_progress < 1.0:
            self._view_anim_progress = min(1.0, self._view_anim_progress + dt / max(0.05, VIEW_TRANSITION_SEC))
            animating = True

        if self._hover_sheen < 1.35:
            self._hover_sheen += dt * 2.35
            animating = True

        if (self._hover or now < self._urgent_pulse_until) and self._has_urgent_quota():
            if now - self._urgent_pulse_ts >= 0.066:
                self._urgent_pulse_ts = now
                animating = True

        if self.is_weather_view() and self._hover:
            self._weather_phase = (self._weather_phase + dt * 0.35) % 1.0
            animating = True

        if self._ring_targets:
            alpha = 1.0 - math.exp(-RING_SMOOTH_RATE * min(0.1, dt))
            for k, tgt in list(self._ring_targets.items()):
                cur = self._ring_display.get(k, tgt)
                diff = tgt - cur
                if abs(diff) > 0.004:
                    self._ring_display[k] = cur + diff * alpha
                    animating = True
                elif cur != tgt:
                    self._ring_display[k] = tgt
                    animating = True

        if not (self._paused or self.is_tiles_view() or self.is_weather_view()):
            cur_w = self.width()
            h = float(self._effective_bar_height())
            if (cur_w, h) != getattr(self, "_cached_avail_sig", None):
                self._sync_schedule_fonts(h)
                left_pad, _r, _ring_gap, tx = schedule_ring_geometry(self._scale, h)
                self._cached_avail = max(20, int(cur_w - tx - left_pad))
                self._cached_avail_sig = (cur_w, h)

            avail = self._cached_avail
            text_w = self._cached_row2_w

            if text_w > avail:
                if self._rest_until and now >= self._rest_until:
                    self._rest_until = 0.0
                if not self._rest_until:
                    loop = text_w + self._gap
                    self._offset += self._speed * dt
                    if self._offset >= loop:
                        self._offset = 0.0
                        self._rest_until = now + self._rest_sec
                    animating = True

        if animating:
            self.repaint()
            self._paint_watchdog(now)
            self._swp_frame(now)

    def _swp_frame(self, now: float) -> None:
        """强制 DWM 重合成跨进程 SetParent 子窗口（严禁移除，详见设计文档 §4.3）。"""
        try:
            import ctypes
            top = self.window()
            if top is not None and int(top.winId()) and not os.environ.get("TOUCHBAR_NO_SWP"):
                swp_flags = 0x1 | 0x2 | 0x4 | 0x10 | 0x20
                hwnd = int(top.winId())
                if now - getattr(self, "_swp_log_ts", 0.0) > 2.0:
                    self._swp_log_ts = now
                    r = (ctypes.c_long * 4)()
                    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
                    _tick_log("swp_pre", r=tuple(r))
                ctypes.windll.user32.InvalidateRect(hwnd, None, False)
                ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, swp_flags)
                if now - getattr(self, "_swp_log_ts", 0.0) < 0.05:
                    r = (ctypes.c_long * 4)()
                    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
                    _tick_log("swp_post", r=tuple(r))
        except Exception:
            pass

    def _paint_watchdog(self, now: float) -> None:
        if not self.isVisible():
            self._paint_stall = 0
            self._paint_stall_fails = 0
            return
        stall = now - self._last_paint_mono
        if stall < 4.0:
            self._paint_stall = 0
            self._paint_stall_fails = 0
            return
        if self._paint_stall == 0:
            self._paint_stall = 1
            top = self.window()
            wh = top.windowHandle() if top else None
            _tick_log(
                "watchdog", lvl=1, stall=round(stall, 1),
                vis=self.isVisible(), upd=self.updatesEnabled(),
                mapped=self.testAttribute(Qt.WidgetAttribute.WA_Mapped),
                wvis=top.isVisible() if top else None,
                exposed=wh.isExposed() if wh else None,
            )
            self.setUpdatesEnabled(False)
            self.setUpdatesEnabled(True)
            try:
                import ctypes
                if top is not None and int(top.winId()):
                    ctypes.windll.user32.InvalidateRect(int(top.winId()), None, True)
                    ctypes.windll.user32.UpdateWindow(int(top.winId()))
            except Exception:
                pass
            return
        if self._paint_stall_fails >= 3:
            return
        self._paint_stall = 2
        self._paint_stall_fails += 1
        _tick_log("watchdog", lvl=2, stall=round(stall, 1), fails=self._paint_stall_fails)
        self.paint_stalled.emit()
        self._last_paint_mono = time.monotonic()

    # ── 绘制分发（委托 CapsuleViewRenderer 与 BarViewStrategy） ──────────────

    def _paint_capsule(self, painter: QPainter, r: QRect) -> None:
        self._capsule_renderer.paint(self, painter, r)

    def _paint_scrolling_row2(self, painter: QPainter, content_rect: QRect, color: QColor | None = None) -> None:
        paint_scrolling_row2(self, painter, content_rect, color)

    def _paint_focus_ring(self, painter: QPainter, rect: QRect, hig: dict) -> None:
        paint_focus_ring(self, painter, rect, hig)

    def _paint_spectrum(self, painter: QPainter, rect: QRect, hig: dict) -> None:
        paint_spectrum(self, painter, rect, hig)

    def paintEvent(self, event) -> None:
        now = time.monotonic()
        self._last_paint_mono = now
        if now - getattr(self, "_paint_log_ts", 0.0) > 2.0:
            self._paint_log_ts = now
            _tick_log("paint", offset=round(self._offset, 1), w=self.width(), visible=self.isVisible())

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self.rect()

        if self._compact or (self.is_capsule_mode() and getattr(self, "_capsule_collapsed", False)):
            self._capsule_renderer.paint(self, painter, r)
            painter.end()
            return

        glass_rect = paint_liquid_glass_island(self, painter, r)
        strat = self._view_registry.get(self.current_view()) or self._view_registry.get(VIEW_SCHEDULE)

        if self._view_anim_progress < 0.999:
            ease = motion.ease_out_cubic(self._view_anim_progress)
            clip_path = QPainterPath()
            rad = max(5.0, 6.0 * self._scale)
            clip_path.addRoundedRect(glass_rect, rad, rad)
            painter.save()
            painter.setClipPath(clip_path)
            painter.setOpacity(0.25 + 0.75 * ease)
            painter.translate(0.0, (1.0 - ease) * 4.5 * self._scale)
            strat.paint(self, painter, r)
            painter.restore()
            painter.end()
            return

        strat.paint(self, painter, r)
        painter.end()

    # ── 鼠标交互与右键菜单（委托 BarContextMenuBuilder） ───────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._try_toggle_view()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._try_toggle_view()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event) -> None:
        event.ignore()

    def _try_toggle_view(self) -> None:
        now = time.monotonic()
        if now - self._last_view_toggle < 0.35:
            return
        self._last_view_toggle = now
        self.toggle_view()

    def _show_menu(self, _pos) -> None:
        BarContextMenuBuilder(self).show_at_cursor()

    def _menu_popup_pos(self, cursor_pos: QPoint, menu_w: int, menu_h: int) -> QPoint:
        return resolve_menu_popup_pos(self._scale, cursor_pos, menu_w, menu_h)

    def _select_theme_mode(self, mode: str) -> None:
        norm = theme.set_theme_mode(mode)
        self._cfg.setdefault("style", {})["themeMode"] = norm
        config_mod.save_config(self._cfg)
        self.apply_style()
        self.refresh_content()
        self.theme_mode_changed.emit(norm)
