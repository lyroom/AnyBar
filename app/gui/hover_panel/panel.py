"""app/gui/hover_panel/panel.py — AnyBar 悬停浮窗主壳层（窗口动画、定位、输入防失焦与卡片注册表编排）"""

from __future__ import annotations

import datetime
import json
import time

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QLinearGradient, QPainter, QPalette, QPen
from PySide6.QtWidgets import QFrame, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from app.core import config as config_mod
from app.platform import glass, win32_utils
from app.styles import theme, tokens

from .cards import (
    DevPanelCard,
    PanelCardContext,
    QuotaPanelCard,
    SchedulePanelCard,
    SystemPanelCard,
    TodoPanelCard,
    WeatherPanelCard,
)
from .primitives import TierCard, make_label, ui_font
from .registry import PanelCardRegistry, build_default_card_registry

HIDE_DELAY_MS = 250
POPUP_ANIM_MS = 255
POPUP_SLIDE_PX = 18
HIDE_ANIM_MS = tokens.MOTION["panel_out"]
RESTORE_ANIM_MS = 120

PANEL_WIDTH = 408
MAX_SCREEN_RATIO = 0.85

_ACTIVE_SCALE = [0.0]


def _detect_scale() -> float:
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    if screen is not None:
        try:
            dpi = float(screen.logicalDotsPerInch())
            if dpi > 0:
                return max(1.0, dpi / 96.0)
        except (RuntimeError, AttributeError):
            pass
    return max(1.0, win32_utils.get_system_dpi() / 96.0)


def _panel_scale() -> float:
    if _ACTIVE_SCALE[0] > 0:
        return _ACTIVE_SCALE[0]
    return _detect_scale()


def _panel_width() -> int:
    return max(PANEL_WIDTH, int(round(PANEL_WIDTH * _panel_scale())))


class HoverPanel(QWidget):
    """悬停浮窗主壳层：统一样式表挂载、定位/弹入淡出动画、防失焦与 PanelCardRegistry 编排。"""

    todo_toggled = Signal(int, bool)
    todo_added = Signal(str)
    todos_cleared = Signal()
    panel_hidden = Signal()

    def __init__(self, card_registry: PanelCardRegistry | None = None):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._registry = card_registry or build_default_card_registry()
        self._cfg: dict = {}
        self._panel_font = QFont()
        self._input_focused = False
        self._anim_opacity: QPropertyAnimation | None = None
        self._anim_pos: QPropertyAnimation | None = None
        self._hide_anim: QPropertyAnimation | None = None
        self._hiding = False
        self._day_expanded = False
        self._done_expanded: bool | None = None
        self._anchor_cache = QRect(100, 100, 300, 40)
        self._shell_built = False
        self._quota_state = None
        self._source_tiles: dict[str, list[dict]] = {}
        self._pending_anchor = (QRect(self._anchor_cache), PANEL_WIDTH)
        self._data_version = 0
        self._last_render_sig = None
        self._rounded_hwnd: int = 0
        self._applied_qss_key: tuple[bool, float] | None = None

        self._container = QWidget(self)
        self._container.setObjectName("panelBody")
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)
        self._outer.addWidget(self._container)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

        self._input_idle_timer = QTimer(self)
        self._input_idle_timer.setSingleShot(True)
        self._input_idle_timer.setInterval(3000)
        self._input_idle_timer.timeout.connect(self._on_input_idle)

        self._minute_timer = QTimer(self)
        self._minute_timer.setInterval(30 * 1000)
        self._minute_timer.timeout.connect(self._refresh_now)

    # ── 卡片子对象只读薄委托（方便外部及测试按职责访问） ───────────────────────

    @property
    def _schedule_card_ctrl(self) -> SchedulePanelCard:
        return self._registry.get("schedule")  # type: ignore[return-value]

    @property
    def _todo_card_ctrl(self) -> TodoPanelCard:
        return self._registry.get("todos")  # type: ignore[return-value]

    @property
    def _system_card_ctrl(self) -> SystemPanelCard:
        return self._registry.get("system")  # type: ignore[return-value]

    @property
    def _weather_card_ctrl(self) -> WeatherPanelCard:
        return self._registry.get("weather")  # type: ignore[return-value]

    @property
    def _quota_card_ctrl(self) -> QuotaPanelCard:
        return self._registry.get("quotas")  # type: ignore[return-value]

    @property
    def _dev_card_ctrl(self) -> DevPanelCard:
        return self._registry.get("dev")  # type: ignore[return-value]

    @property
    def _header(self):
        return self._schedule_card_ctrl.header

    @property
    def _todo_card(self):
        return self._todo_card_ctrl.card

    @property
    def _todo_count(self):
        return self._todo_card_ctrl.count_badge

    @property
    def _done_drawer(self):
        return self._todo_card_ctrl.done_drawer

    @property
    def _todo_rows(self):
        return self._todo_card_ctrl.rows

    @property
    def _quota_card(self):
        return self._quota_card_ctrl.card

    @property
    def _quota_tiles(self):
        return self._quota_card_ctrl.tiles

    @property
    def _system_card(self):
        return self._system_card_ctrl.card

    @property
    def _system_boxes(self):
        return self._system_card_ctrl.boxes

    @property
    def _system_gauges(self):
        return self._system_card_ctrl.gauges

    @property
    def _system_detail_labels(self):
        return self._system_card_ctrl.detail_labels

    @property
    def _weather_card(self):
        return self._weather_card_ctrl.card

    @property
    def _weather_boxes(self):
        return self._weather_card_ctrl.boxes

    @property
    def _temp_range_bars(self):
        return self._weather_card_ctrl.temp_range_bars

    @property
    def _dev_card(self):
        return self._dev_card_ctrl.card

    @property
    def _dev_widgets(self):
        return self._dev_card_ctrl.widgets

    # ── 数据上下文构造与外部数据注入 ──────────────────────────────────────────

    def _make_context(self, dark: bool | None = None, scale: float | None = None) -> PanelCardContext:
        d = getattr(self, "_dark", theme.is_system_dark()) if dark is None else dark
        s = getattr(self, "_scale", None) or _panel_scale() if scale is None else scale
        return PanelCardContext(
            panel=self,
            cfg=self._cfg,
            dark=bool(d),
            scale=float(s),
            source_tiles=self._source_tiles,
            quota_state=self._quota_state,
        )

    def _apply_panel_qss(self, dark: bool, scale: float) -> None:
        key = (bool(dark), round(float(scale), 3))
        if self._applied_qss_key != key:
            self._applied_qss_key = key
            self.setStyleSheet(theme.hover_panel_qss(dark, scale))

    def set_panel_font(self, font: QFont) -> None:
        self._panel_font = font

    def set_music(self, music: dict) -> None:
        if isinstance(music, dict) and (music.get("title") or music.get("lyrics")):
            self._cfg["music"] = music
        else:
            self._cfg.pop("music", None)
        self._data_version += 1
        if self.isVisible():
            self.popup(self._cfg, self._anchor_cache)

    def set_quota_state(self, state) -> None:
        self._quota_state = state
        if self.isVisible():
            if not self._registry.dispatch_inplace_update("quota", self._make_context()):
                self._atomic_rerender_and_fit()
        else:
            self._data_version += 1

    def set_source_tiles(self, source_id: str, tiles_list: list[dict]) -> None:
        self._source_tiles[source_id] = list(tiles_list or [])
        if not self.isVisible():
            self._data_version += 1
            return
        if not self._registry.is_source_card_shown(source_id, self._cfg):
            return
        if not self._registry.dispatch_inplace_update(source_id, self._make_context()):
            self._atomic_rerender_and_fit()

    def _atomic_rerender_and_fit(self) -> None:
        was_upd = self.updatesEnabled()
        self.setUpdatesEnabled(False)
        try:
            self._render()
            self._last_render_sig = self._render_signature(getattr(self, "_scale", _panel_scale()))
            self._fixup_height(invalidate=True)
        finally:
            self.setUpdatesEnabled(was_upd)

    # ── 窗口弹出、隐藏与生命周期 ──────────────────────────────────────────────

    def _stop_anims(self) -> None:
        for anim in (self._anim_opacity, self._anim_pos):
            if anim is not None:
                anim.stop()
                anim.deleteLater()
        self._anim_opacity = None
        self._anim_pos = None
        if self._hide_anim is not None:
            self._hide_anim.stop()
            self._hide_anim.deleteLater()
            self._hide_anim = None

    def _is_input_actively_focused(self) -> bool:
        edit = getattr(self, "_add_input", None)
        if not self._input_focused or edit is None or not edit.isVisible():
            return False
        return bool(edit.hasFocus() and self.isActiveWindow())

    def _cursor_inside_panel_or_anchor(self) -> bool:
        g_pos = QCursor.pos()
        if self.isVisible() and self.frameGeometry().contains(g_pos):
            return True
        anchor = getattr(self, "_anchor_cache", None)
        return bool(anchor is not None and anchor.contains(g_pos))

    def hide(self) -> None:
        if not self.isVisible() or self._hiding:
            return
        if self._is_input_actively_focused() and self._add_input.text():
            return
        self._input_focused = False
        self._input_idle_timer.stop()
        self._stop_anims()
        self._hiding = True
        self._minute_timer.stop()
        start = self.windowOpacity()
        self._hide_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._hide_anim.setDuration(HIDE_ANIM_MS)
        self._hide_anim.setStartValue(start)
        self._hide_anim.setEndValue(0.0)
        self._hide_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._hide_anim.finished.connect(self._finish_animated_hide)
        self._hide_anim.start()

    def _finish_animated_hide(self) -> None:
        self._hiding = False
        self.setWindowOpacity(1.0)
        super().hide()
        self._stop_anims()

    def hideEvent(self, event):
        self._input_focused = False
        self._input_idle_timer.stop()
        self._minute_timer.stop()
        self._stop_anims()
        self._registry.stop_all_animations()
        self._hiding = False
        self.setWindowOpacity(1.0)
        super().hideEvent(event)
        self.panel_hidden.emit()

    def _on_input_idle(self) -> None:
        edit = getattr(self, "_add_input", None)
        if edit is not None and edit.hasFocus():
            edit.clearFocus()
        self._input_focused = False
        if not self._cursor_inside_panel_or_anchor():
            self._hide_timer.start(HIDE_DELAY_MS)

    def close_now(self) -> None:
        self._input_focused = False
        self._hide_timer.stop()
        self._input_idle_timer.stop()
        self._stop_anims()
        self._registry.stop_all_animations()
        self._hiding = False
        self.setWindowOpacity(1.0)
        self._minute_timer.stop()
        super().hide()

    def keep_alive(self) -> None:
        self._hide_timer.stop()
        self._input_idle_timer.stop()
        if self._hiding or (
            self._hide_anim is not None
            and self._hide_anim.state() == QPropertyAnimation.State.Running
        ):
            self._hiding = False
            if self._hide_anim is not None:
                self._hide_anim.stop()
                self._hide_anim.deleteLater()
                self._hide_anim = None
            start = self.windowOpacity()
            if start < 1.0:
                restore = QPropertyAnimation(self, b"windowOpacity", self)
                restore.setDuration(RESTORE_ANIM_MS)
                restore.setStartValue(start)
                restore.setEndValue(1.0)
                restore.setEasingCurve(QEasingCurve.Type.OutCubic)
                self._hide_anim = restore
                restore.start()
        if self.isVisible():
            self._minute_timer.start()

    def schedule_hide(self) -> None:
        if self._is_input_actively_focused():
            self._input_idle_timer.start()
            return
        self._input_focused = False
        self._input_idle_timer.stop()
        self._hide_timer.start(HIDE_DELAY_MS)

    def _render_signature(self, scale: float) -> tuple:
        cfg = self._cfg or {}
        try:
            cfg_fp = json.dumps(
                {
                    "panelCards": cfg.get("panelCards"),
                    "schedule": cfg.get("schedule"),
                    "defaultText": cfg.get("defaultText"),
                    "todos": cfg.get("todos"),
                    "quotas": cfg.get("quotas"),
                    "sources": cfg.get("sources"),
                    "music": cfg.get("music"),
                    "scheduleBarColor": (cfg.get("style") or {}).get("scheduleBarColor"),
                },
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
        except Exception:
            cfg_fp = str(time.monotonic())
        return (theme.is_system_dark(), round(float(scale), 3), self._data_version, cfg_fp)

    def popup(self, cfg: dict, anchor_rect, width=None) -> None:
        self._anchor_cache = QRect(anchor_rect)
        was_visible = self.isVisible()
        self._cfg = cfg
        scale = _detect_scale()
        if abs(scale - getattr(self, "_scale", scale)) > 0.01:
            self._shell_built = False
            self._last_render_sig = None
        _ACTIVE_SCALE[0] = scale
        self._scale = scale
        width = _panel_width()
        self._pending_anchor = (QRect(anchor_rect), width)

        if was_visible:
            was_upd = self.updatesEnabled()
            self.setUpdatesEnabled(False)
            try:
                if not self._shell_built:
                    self._build_shell()
                    self._last_render_sig = None
                sig = self._render_signature(scale)
                changed = sig != self._last_render_sig
                if changed:
                    self._render()
                    self._last_render_sig = sig
                else:
                    self._refresh_now()
                height = self._compute_height(width, invalidate=changed)
                x, y = self._place(anchor_rect, width, height)
                target_geo = QRect(x, y, width, height)
                if self.geometry() != target_geo:
                    self.setGeometry(target_geo)
            finally:
                self.setUpdatesEnabled(was_upd)
            return

        if not self._shell_built:
            self._build_shell()
            self._last_render_sig = None
        sig = self._render_signature(scale)
        if sig != self._last_render_sig:
            self._render()
            self._last_render_sig = sig
        else:
            self._refresh_now()
        height = self._compute_height(width, invalidate=True)
        x, y = self._place(anchor_rect, width, height)
        self.popup_animated(QPoint(x, y), QSize(width, height))
        QTimer.singleShot(0, self._fixup_height)

    @staticmethod
    def _screen_for_anchor(anchor_rect: QRect | None = None):
        if anchor_rect is not None and not anchor_rect.isNull():
            scr = QGuiApplication.screenAt(anchor_rect.center())
            if scr is not None:
                return scr
        return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

    def _place(self, anchor_rect, width: int, height: int):
        screen = self._screen_for_anchor(anchor_rect)
        avail = screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)
        x = anchor_rect.right() - width
        if anchor_rect.top() < avail.top() + max(180, height // 2):
            y = anchor_rect.bottom() + 8
        else:
            y = anchor_rect.top() - height - 8
        x = max(avail.left() + 4, min(x, avail.right() - width - 4))
        y = max(avail.top() + 4, min(y, avail.bottom() - height - 4))
        return x, y

    def popup_animated(self, target_pos: QPoint, size: QSize) -> None:
        self._stop_anims()
        self._hiding = False
        self.setWindowOpacity(0.0)
        slide = tokens.spx(POPUP_SLIDE_PX, getattr(self, "_scale", 1.0))
        start_pos = QPoint(target_pos.x(), target_pos.y() + slide)
        self.setGeometry(QRect(start_pos, size))
        self.show()
        self.raise_()
        self.activateWindow()
        self._apply_glass()

        spring = QEasingCurve(QEasingCurve.Type.OutBack)
        spring.setOvershoot(0.72)

        self._anim_pos = QPropertyAnimation(self, b"pos", self)
        self._anim_pos.setDuration(POPUP_ANIM_MS)
        self._anim_pos.setStartValue(start_pos)
        self._anim_pos.setEndValue(target_pos)
        self._anim_pos.setEasingCurve(spring)
        self._anim_pos.start()

        self._anim_opacity = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim_opacity.setDuration(int(POPUP_ANIM_MS * 0.85))
        self._anim_opacity.setStartValue(0.0)
        self._anim_opacity.setEndValue(1.0)
        self._anim_opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_opacity.finished.connect(self._on_popup_anim_done)
        self._anim_opacity.start()

        self._registry.play_all_entrances()

    def _on_popup_anim_done(self) -> None:
        self._minute_timer.start()

    # ── 壳层构建、绘制与卡片编排渲染 ──────────────────────────────────────────

    def _compute_height(self, width: int, invalidate: bool = False) -> int:
        scale = getattr(self, "_scale", None) or _panel_scale()
        pad = self._pad()
        avail_w = max(120, width - self._pad_x() * 2)
        if self._body.maximumWidth() != avail_w:
            self._body.setMaximumWidth(avail_w)
        if invalidate:
            self._content.invalidate()
            self._content.activate()
        hint = self._body.sizeHint().height()
        hfw = self._content.heightForWidth(avail_w) if self._content.hasHeightForWidth() else 0
        content_h = max(hint, hfw, 0)
        total = content_h + pad * 2
        anchor_rect = self._pending_anchor[0] if getattr(self, "_pending_anchor", None) else self._anchor_cache
        screen = self._screen_for_anchor(anchor_rect)
        limit = int(screen.availableGeometry().height() * MAX_SCREEN_RATIO) if screen is not None else 1000
        return max(int(180 * scale), min(total, limit))

    def _fixup_height(self, invalidate: bool = False) -> None:
        if not self.isVisible():
            return
        anchor_rect, width = self._pending_anchor
        height = self._compute_height(width, invalidate=invalidate)
        x, y = self._place(anchor_rect, width, height)
        target_geo = QRect(x, y, width, height)
        pos_animating = (
            self._anim_pos is not None
            and self._anim_pos.state() == QPropertyAnimation.State.Running
        )
        if pos_animating:
            if self.size() != QSize(width, height):
                self.resize(width, height)
            self._anim_pos.setEndValue(QPoint(x, y))
        elif self.geometry() != target_geo:
            self.setGeometry(target_geo)

    def _apply_glass(self) -> None:
        hwnd = int(self.winId())
        if hwnd and hwnd != self._rounded_hwnd:
            glass.round_corners(hwnd)
            self._rounded_hwnd = hwnd

    def _px(self, v: float) -> int:
        return tokens.spx(v, getattr(self, "_scale", 1.0))

    def _pad_x(self) -> int:
        return self._px(10)

    def _pad(self) -> int:
        return self._px(10)

    def _build_shell(self) -> None:
        self._shell_built = True
        dark = theme.is_system_dark()
        scale = getattr(self, "_scale", None) or _panel_scale()
        self._scale = scale
        self._dark = dark
        self._apply_panel_qss(dark, scale)

        pad = self._pad()
        pad_x = self._pad_x()
        if getattr(self, "_inner", None) is None:
            self._inner = QVBoxLayout(self._container)
        else:
            self._clear_layout(self._inner)
        self._inner.setContentsMargins(pad_x, pad, pad_x, pad)
        self._inner.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("panelScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._body = QWidget()
        self._body.setObjectName("panelCanvas")
        self._body.setMinimumWidth(0)
        self._content = QVBoxLayout(self._body)
        self._content.setContentsMargins(0, 0, 0, 0)
        self._content.setSpacing(self._px(8))
        self._scroll.setWidget(self._body)
        self._inner.addWidget(self._scroll, 1)

        self._add_input = QLineEdit()
        self._add_input.setObjectName("quickTodoInput")
        self._add_input.setPlaceholderText("+ 添加待办事项，回车保存...")
        self._add_input.setFont(ui_font(12 * scale, 400))
        self._add_input.setFixedHeight(max(32, self._px(34)))
        self._set_placeholder_color(dark)
        self._add_input.returnPressed.connect(lambda e=self._add_input: self._on_add_todo(e))
        self._add_input.installEventFilter(self)
        self._add_input.setParent(None)

    def paintEvent(self, event):
        dark = getattr(self, "_dark", False)
        t = tokens.get_tokens(dark)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        rad = float(self._px(tokens.RADIUS["panel"]))

        bg_grad = QLinearGradient(0.0, r.top(), 0.0, r.bottom())
        bg_grad.setColorAt(0.0, QColor(t.canvas_top))
        bg_grad.setColorAt(1.0, QColor(t.canvas))
        p.setPen(QPen(QColor(t.canvas_border_hex), 1.0))
        p.setBrush(bg_grad)
        p.drawRoundedRect(r, rad, rad)

        inner_r = r.adjusted(0.9, 0.9, -0.9, -0.9)
        rim_grad = QLinearGradient(0.0, inner_r.top(), 0.0, inner_r.bottom())
        rim_grad.setColorAt(0.0, QColor(*t.rim_top))
        rim_grad.setColorAt(0.5, QColor(*t.rim_mid))
        rim_grad.setColorAt(1.0, QColor(*t.rim_bottom))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(rim_grad, 1.0))
        p.drawRoundedRect(inner_r, max(4.0, rad - 0.9), max(4.0, rad - 0.9))
        p.end()
        super().paintEvent(event)

    def _set_placeholder_color(self, dark: bool) -> None:
        t = tokens.get_tokens(dark)
        pal_obj = self._add_input.palette()
        pal_obj.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.text_muted))
        self._add_input.setPalette(pal_obj)

    def _clear_layout(self, lay) -> None:
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _refresh_now(self) -> None:
        if not self.isVisible():
            return
        self._registry.refresh_all(self._make_context())

    def _valid_todos(self):
        out = []
        for idx, item in enumerate(self._cfg.get("todos", []) or []):
            if isinstance(item, dict) and str(item.get("title", "")).strip():
                out.append((idx, item))
        return out

    def _render(self) -> None:
        dark = theme.is_system_dark()
        t = tokens.get_tokens(dark)
        scale = getattr(self, "_scale", None) or _panel_scale()
        self._dark = dark
        self._apply_panel_qss(dark, scale)

        scroll_bar = self._scroll.verticalScrollBar() if getattr(self, "_scroll", None) is not None else None
        prev_scroll_y = scroll_bar.value() if (scroll_bar is not None and self.isVisible()) else 0
        input_had_focus = bool(getattr(self, "_add_input", None) is not None and self._add_input.hasFocus())

        was_upd = self.updatesEnabled()
        self.setUpdatesEnabled(False)
        try:
            if getattr(self, "_add_input", None) is not None:
                self._add_input.setParent(None)
            self._clear_layout(self._content)
            self._set_placeholder_color(dark)

            ctx = self._make_context(dark=dark, scale=scale)
            rendered_count = self._registry.render_into(ctx, self._content)

            if rendered_count == 0:
                empty_card = TierCard(dark, scale)
                ev = QVBoxLayout(empty_card)
                p_m = tokens.spx(18, scale, lo=14)
                ev.setContentsMargins(p_m, p_m, p_m, p_m)
                empty_lbl = make_label(
                    "悬浮窗卡片已全部隐藏\n可在「设置 - 界面与浮窗」中勾选开启",
                    12 * scale, t.text_muted, 500, role="muted",
                )
                empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                ev.addWidget(empty_lbl)
                self._content.addWidget(empty_card)

            self._content.addStretch(1)
            self._content.activate()
            if scroll_bar is not None and prev_scroll_y > 0:
                scroll_bar.setValue(min(prev_scroll_y, scroll_bar.maximum()))
            if input_had_focus and self._add_input.parent() is not None:
                self._add_input.setFocus()
        finally:
            self.setUpdatesEnabled(was_upd)
        self.update()

    # ── 卡片交互回调（待办原位更新 / 抽屉展开） ───────────────────────────────

    def sync_todos_inplace(self, cfg: dict | None = None, anchor_rect: QRect | None = None,
                           keep_focus: bool = False) -> bool:
        if cfg is not None:
            self._cfg = cfg
        if anchor_rect is not None:
            self._anchor_cache = QRect(anchor_rect)
            self._pending_anchor = (QRect(anchor_rect), _panel_width())

        todo_ctrl = self._todo_card_ctrl
        if (
            not self.isVisible()
            or todo_ctrl.card is None
            or todo_ctrl.card.parent() is None
            or todo_ctrl.items_lay is None
        ):
            self._data_version += 1
            return False

        dark = getattr(self, "_dark", theme.is_system_dark())
        scale = getattr(self, "_scale", None) or _panel_scale()
        scroll_bar = self._scroll.verticalScrollBar() if getattr(self, "_scroll", None) is not None else None
        prev_scroll_y = scroll_bar.value() if scroll_bar is not None else 0

        was_upd = self.updatesEnabled()
        self.setUpdatesEnabled(False)
        try:
            todo_ctrl.populate_items(self, dark, scale, self._valid_todos())
            self._refresh_now()
            self._last_render_sig = self._render_signature(scale)
            todo_ctrl.items_lay.activate()
            if todo_ctrl.card.layout() is not None:
                todo_ctrl.card.layout().activate()
            self._fixup_height(invalidate=True)
            if scroll_bar is not None:
                scroll_bar.setValue(min(prev_scroll_y, scroll_bar.maximum()))
            if keep_focus and self._add_input is not None and self._add_input.isVisible():
                self._add_input.setFocus()
                self._input_focused = True
                self._hide_timer.stop()
                if not self._cursor_inside_panel_or_anchor():
                    self._input_idle_timer.start()
        finally:
            self.setUpdatesEnabled(was_upd)
        todo_ctrl.card.update()
        return True

    def _on_toggle_done_section(self) -> None:
        self._done_expanded = not bool(self._done_expanded)
        todo_ctrl = self._todo_card_ctrl
        if todo_ctrl.done_drawer is not None:
            todos = self._valid_todos()
            done_n = sum(1 for _, item in todos if item.get("done"))
            if todo_ctrl.done_toggle_btn is not None:
                arrow = "▾" if self._done_expanded else "▸"
                todo_ctrl.done_toggle_btn.setText(f"{arrow} 已完成 ({done_n})")
            todo_ctrl.done_drawer.set_expanded(self._done_expanded, animated=True)
        else:
            self._render()
            QTimer.singleShot(0, self._fixup_height)

    def _on_clear_done(self) -> None:
        self.todos_cleared.emit()

    def _on_expand_day(self) -> None:
        self._day_expanded = not self._day_expanded
        hdr = self._header
        if hdr is not None:
            cur = config_mod.current_schedule(self._cfg, datetime.datetime.now())
            hdr.set_expanded(self._day_expanded, self._cfg.get("schedule", []), cur, animated=True)
        else:
            self._render()
            QTimer.singleShot(0, self._fixup_height)

    def _on_todo_check(self, index: int, done: bool) -> None:
        self.todo_toggled.emit(index, done)
        todos = self._valid_todos()
        if not todos:
            return
        done_n = sum(1 for _, item in todos if item.get("done"))
        if self._todo_count is not None:
            self._todo_count.setText(f"已完成 {done_n}/{len(todos)}")

    def _on_add_todo(self, edit: QLineEdit) -> None:
        text = edit.text().strip()
        if not text:
            return
        edit.clear()
        self._input_idle_timer.stop()
        self.todo_added.emit(text)

    # ── 事件过滤与焦点管理 ────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is getattr(self, "_add_input", None):
            ev_type = event.type()
            if ev_type == QEvent.Type.MouseButtonPress:
                self._input_focused = True
                self._input_idle_timer.stop()
                self._hide_timer.stop()
                self.activateWindow()
                self.raise_()
                obj.setFocus()
                try:
                    import ctypes
                    ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
                except Exception:
                    pass
            elif ev_type == QEvent.Type.FocusIn:
                self._input_focused = True
                self._input_idle_timer.stop()
            elif ev_type == QEvent.Type.FocusOut:
                self._input_focused = False
                self._input_idle_timer.stop()
                if self.isVisible() and not self._cursor_inside_panel_or_anchor():
                    self._hide_timer.start(HIDE_DELAY_MS)
            elif ev_type == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    obj.clearFocus()
                    self._input_focused = False
                    self._input_idle_timer.stop()
                    self.hide()
                    return True
                self._hide_timer.stop()
                if not self._cursor_inside_panel_or_anchor():
                    self._input_idle_timer.start()
            elif ev_type == QEvent.Type.InputMethod:
                self._hide_timer.stop()
                if not self._cursor_inside_panel_or_anchor():
                    self._input_idle_timer.start()
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        edit = getattr(self, "_add_input", None)
        if edit is not None and edit.isVisible() and edit.hasFocus():
            local_in_edit = edit.mapFrom(self, event.position().toPoint())
            if not edit.rect().contains(local_in_edit):
                edit.clearFocus()
                self._input_focused = False
                self._input_idle_timer.stop()
        super().mousePressEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowDeactivate:
            self._input_focused = False
            self._input_idle_timer.stop()
            edit = getattr(self, "_add_input", None)
            if edit is not None and edit.hasFocus():
                edit.clearFocus()
            if self.isVisible() and not self._cursor_inside_panel_or_anchor():
                self.hide()
        super().changeEvent(event)

    def enterEvent(self, event):
        self._hide_timer.stop()
        self._input_idle_timer.stop()
        self.keep_alive()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.schedule_hide()
        super().leaveEvent(event)
