"""app/gui/settings/dialog.py — AnyBar 设置中心（Mediator 壳层 + Page Presenter 组合）

职责严格收敛为：
- 窗口生命周期、多屏 DPI 跟随、居中尺寸记忆与 Win32 标题栏深浅色同步；
- 顶部滑动导航（SlidingSegmentedControl）与 6 大页面（BaseSettingsPage）的协调；
- 防抖实时预览、主题一键即时切换、快照回滚（应用后同步 snapshot 防止取消分叉）；
- 根级别外部 QSS 样式表挂载（零散内联 QSS 全部迁入 app/styles/qss/settings.qss）。
"""

from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from app.core import config as config_mod
from app.gui import widgets as ui_parts
from app.gui.widgets import motion
from app.platform import glass, win32_utils
from app.styles import qss_engine, theme, tokens

from .form_helpers import SettingsFormContext, SettingsMetrics, normalize_time_str
from .pages import (
    AppearancePage,
    BarStylePage,
    BaseSettingsPage,
    ExtensionsPage,
    PluginsPage,
    SchedulePage,
    TodoPage,
)
from .quota_controller import QuotaSyncController

# 兼容测试与调用方导入的时间规范化辅助函数
_normalize_time_str = normalize_time_str


def _dlg_scale() -> float:
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    if screen is not None:
        try:
            dpi = float(screen.logicalDotsPerInch())
            if dpi > 0:
                return max(1.0, dpi / 96.0)
        except (RuntimeError, AttributeError):
            pass
    return max(1.0, win32_utils.get_system_dpi() / 96.0)


class SettingsDialog(QDialog):
    """AnyBar 设置中心主窗口（Mediator）：协调 6 个独立页面控制器与配置快照。"""

    _last_dialog_size: tuple[int, int] | None = None

    def __init__(self, parent, cfg: dict[str, Any], preview_callback=None):
        super().__init__(parent)
        self.setWindowTitle("AnyBar · 设置中心")
        self.setWindowIcon(ui_parts.app_window_icon())
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setSizeGripEnabled(True)

        theme.apply_theme_mode_from_cfg(cfg)
        self._dark = theme.is_system_dark()
        self._scale = _dlg_scale()
        self._apply_base_font()
        self._metrics = SettingsMetrics.from_scale(self._scale)

        if SettingsDialog._last_dialog_size is not None:
            mem_w, mem_h = SettingsDialog._last_dialog_size
            init_w = self._px(max(760, mem_w))
            init_h = self._px(max(540, mem_h))
        else:
            init_w = self._px(860)
            init_h = self._px(680)
        self.resize(init_w, init_h)
        self.setMinimumSize(self._px(680), self._px(490))

        self._live_cfg = cfg
        self._cfg = copy.deepcopy(cfg)
        self._snapshot = copy.deepcopy(cfg)
        self._preview_callback = preview_callback
        self._toast: motion.ToastBanner | None = None
        self._form_ctx: SettingsFormContext | None = None

        self._preview_debounce = QTimer(self)
        self._preview_debounce.setSingleShot(True)
        self._preview_debounce.setInterval(250)
        self._preview_debounce.timeout.connect(self._on_preview)

        self._quota_sync = QuotaSyncController(self)
        self._quota_sync.rows_updated.connect(self._on_quota_rows_updated)
        self._quota_sync.sync_finished.connect(self._on_quota_test_done)

        self._schedule_page = SchedulePage()
        self._todo_page = TodoPage()
        self._bar_style_page = BarStylePage()
        self._appearance_page = AppearancePage(self._on_theme_mode_selected)
        self._extensions_page = ExtensionsPage(self._quota_sync)
        self._plugins_page = PluginsPage()
        self._pages: list[BaseSettingsPage] = [
            self._schedule_page,
            self._todo_page,
            self._bar_style_page,
            self._appearance_page,
            self._extensions_page,
            self._plugins_page,
        ]

        self.setStyleSheet(theme.settings_qss(self._dark, self._metrics.cb_ind, self._scale))
        self._build_ui()
        self._load()
        self._connect_preview()

        self._screen_hooked = False
        self._placed = False

    def _px(self, base_px: float) -> int:
        return tokens.spx(base_px, self._scale)

    def _apply_base_font(self) -> None:
        self.setFont(theme.ui_font(12.5 * self._scale, 400))

    # ── UI 构建与重建 ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._root = QVBoxLayout(self)
        self._fill_ui()
        self._toast = motion.ToastBanner(self, dark=self._dark, scale=self._scale)

    def _fill_ui(self) -> None:
        ctx = SettingsFormContext(
            dialog=self,
            dark=self._dark,
            scale=self._scale,
            schedule_preview=self._schedule_preview,
            trigger_preview=self._on_preview,
            show_toast=self._show_toast,
        )
        self._form_ctx = ctx
        m = ctx.metrics

        v = self._root
        v.setContentsMargins(self._px(18), self._px(14), self._px(18), self._px(14))
        v.setSpacing(self._px(12))

        # 顶部居中液态滑块分段导航 + 右侧一键浅色/深色快捷切换按钮
        track_row = QHBoxLayout()
        track_row.setContentsMargins(0, 0, 0, 0)
        track_row.setSpacing(self._px(10))

        self._quick_theme_btn = ctx.make_action_btn(
            "浅色" if self._dark else "深色",
            "sun" if self._dark else "moon",
        )
        self._quick_theme_btn.setFixedHeight(self._px(34))
        self._quick_theme_btn.setToolTip(
            "一键切换为浅色模式" if self._dark else "一键切换为深色模式"
        )
        self._quick_theme_btn.clicked.connect(self._on_quick_toggle_theme)

        left_spacer = QWidget()
        left_spacer.setFixedWidth(self._quick_theme_btn.sizeHint().width())
        qss_engine.set_transparent(left_spacer)
        track_row.addWidget(left_spacer)
        track_row.addStretch(1)

        self._seg = ui_parts.SlidingSegmentedControl(
            [p.title for p in self._pages],
            self._dark,
            font=self.font(),
            scale=self._scale,
        )
        track_row.addWidget(self._seg)
        track_row.addStretch(1)
        track_row.addWidget(self._quick_theme_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        v.addLayout(track_row)

        # 平滑淡入页面栈
        self._stack = motion.AnimatedStackedWidget(duration=tokens.MOTION["fast"])
        for page in self._pages:
            self._stack.addWidget(page.build(ctx))
        v.addWidget(self._stack, 1)
        self._seg.currentChanged.connect(self._on_seg_changed)

        # 底部分割线 + 操作栏
        foot_div = QFrame()
        foot_div.setFixedHeight(1)
        qss_engine.set_role(foot_div, "divider", polish=False)
        v.addWidget(foot_div)

        restore_btn = ctx.make_action_btn("恢复默认", "reset", ghost=True)
        cancel_btn = ctx.make_action_btn("取消")
        apply_btn = ctx.make_action_btn("应用")
        save_btn = ctx.make_action_btn("保存并关闭", primary=True)

        restore_btn.clicked.connect(self._on_restore)
        apply_btn.clicked.connect(self._on_apply)
        save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self._on_cancel)

        for b in (restore_btn, apply_btn, save_btn, cancel_btn):
            b.setFixedHeight(m.btn_h)
            b.setMinimumWidth(m.btn_min_w)
        save_btn.setMinimumWidth(m.save_btn_w)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, self._px(2), 0, 0)
        btn_row.setSpacing(self._px(10))
        btn_row.addWidget(restore_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(save_btn)
        v.addLayout(btn_row)

    def _rebuild_ui(self) -> None:
        self._clear_layout(self._root)
        self._fill_ui()

    def _clear_layout(self, lay) -> None:
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                self._clear_layout(sub)

    def _show_toast(self, text: str, kind: str = "ok") -> None:
        if self._toast is not None and self.isVisible():
            self._toast.show_message(text, kind=kind)

    # ── 窗口事件与多屏 DPI 适配 ─────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        try:
            hwnd = int(self.winId())
            if hwnd:
                glass.style_titlebar(hwnd, self._dark)
        except Exception:
            pass
        self._hook_screen()
        screen = self._screen()
        self._apply_screen_scale(screen)
        if not self._placed:
            self._fit_to_screen(screen)
            self._placed = True
            self._center_on_screen(screen)
        self._sync_todo_done_state()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_placed", False) and self._scale > 0 and not self.isMaximized():
            w_log = int(round(self.width() / self._scale))
            h_log = int(round(self.height() / self._scale))
            SettingsDialog._last_dialog_size = (w_log, h_log)

    def _on_seg_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        if index == 1:
            self._sync_todo_done_state()
        elif index == 4:
            self._ensure_quota_tab_width()

    def _ensure_quota_tab_width(self) -> None:
        if self.isMaximized():
            return
        screen = self._screen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        left, top, right, bottom = self._frame_margins()
        max_w = max(self._px(400), avail.width() - left - right)
        target_w = min(self._px(820), max_w)
        if self.width() < target_w:
            cur_geo = self.geometry()
            diff = target_w - cur_geo.width()
            new_x = cur_geo.x() - diff // 2
            new_x = max(avail.left() + left, min(new_x, avail.right() - right - target_w))
            self.setGeometry(new_x, cur_geo.y(), target_w, cur_geo.height())

    def _sync_todo_done_state(self) -> None:
        self._todo_page.sync_done_state(self._live_cfg, self._cfg)

    @staticmethod
    def _screen():
        return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

    def _hook_screen(self) -> None:
        if self._screen_hooked:
            return
        handle = self.windowHandle()
        if handle is None:
            return
        handle.screenChanged.connect(self._on_screen_changed)
        self._screen_hooked = True

    def _on_screen_changed(self, screen) -> None:
        QTimer.singleShot(0, lambda s=screen: self._apply_screen_scale(s))

    def _frame_margins(self):
        handle = self.windowHandle()
        if handle is not None:
            try:
                fm = handle.frameMargins()
                return (
                    max(0, fm.left()),
                    max(0, fm.top()),
                    max(0, fm.right()),
                    max(0, fm.bottom()),
                )
            except (RuntimeError, AttributeError):
                pass
        geo = self.frameGeometry()
        cli = self.geometry()
        return (
            max(0, cli.x() - geo.x()),
            max(0, cli.y() - geo.y()),
            max(0, geo.right() - cli.right()),
            max(0, geo.bottom() - cli.bottom()),
        )

    def _fit_to_screen(self, screen) -> None:
        if screen is None:
            screen = self._screen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        left, top, right, bottom = self._frame_margins()
        max_w = max(self._px(400), avail.width() - left - right)
        max_h = max(self._px(300), avail.height() - top - bottom)
        if SettingsDialog._last_dialog_size is not None:
            mem_w, mem_h = SettingsDialog._last_dialog_size
            want_w = min(max_w, max(self._px(740), self._px(mem_w)))
            want_h = min(max_h, max(self._px(540), self._px(mem_h)))
        else:
            want_w = min(self._px(820), max_w)
            want_h = min(self._px(670), max_h)
        self.setMinimumSize(min(self._px(660), want_w), min(self._px(490), want_h))
        self.resize(want_w, want_h)

    def _center_on_screen(self, screen) -> None:
        if screen is None:
            return
        geo = screen.availableGeometry()
        left, top, right, bottom = self._frame_margins()
        frame_w = self.width() + left + right
        frame_h = self.height() + top + bottom
        x = geo.center().x() - frame_w // 2
        y = geo.center().y() - frame_h // 2
        x = max(geo.left(), min(x, geo.right() - frame_w + 1))
        y = max(geo.top(), min(y, geo.bottom() - frame_h + 1))
        self.move(x + left, y + top)

    @staticmethod
    def _screen_scale(screen) -> float:
        if screen is None:
            return 1.0
        try:
            dpi = float(screen.logicalDotsPerInch())
        except (RuntimeError, AttributeError):
            return 1.0
        return max(1.0, dpi / 96.0) if dpi > 0 else 1.0

    def _apply_screen_scale(self, screen=None) -> None:
        if screen is None or not hasattr(screen, "availableGeometry"):
            screen = self._screen()
        scale = self._screen_scale(screen)
        if abs(scale - self._scale) < 0.01:
            return
        cur_tab = self._seg.currentIndex() if hasattr(self, "_seg") else 0
        self._collect_config()
        self._scale = scale
        self._apply_base_font()
        self._metrics = SettingsMetrics.from_scale(self._scale)
        self.setStyleSheet(theme.settings_qss(self._dark, self._metrics.cb_ind, self._scale))
        for page in self._pages:
            page.on_scale_changed(self._dark, self._scale)
        if self._toast is not None:
            self._toast.set_dark_scale(self._dark, self._scale)
        self._rebuild_ui()
        self._load()
        self._connect_preview()
        self._seg.setCurrentIndex(cur_tab, notify=False)
        self._stack.setCurrentIndex(cur_tab)
        self._fit_to_screen(screen)

    # ── 数据编排与实时主题切换 ──────────────────────────────────────────────

    def _load(self) -> None:
        for page in self._pages:
            page.load(self._cfg)

    def _connect_preview(self) -> None:
        for page in self._pages:
            page.connect_preview()

    def _schedule_preview(self) -> None:
        self._preview_debounce.start()

    def _collect_config(self) -> None:
        for page in self._pages:
            page.collect(self._cfg)

        style = self._cfg.setdefault("style", {})
        live_bar_view = (self._live_cfg.get("style") or {}).get("barView")
        if live_bar_view in ("schedule", "quota", "tiles"):
            style["barView"] = live_bar_view
            if isinstance(self._snapshot.get("style"), dict):
                self._snapshot["style"]["barView"] = live_bar_view

    def _on_preview(self) -> None:
        self._collect_config()
        if self._preview_callback:
            self._preview_callback(self._cfg)

    def _on_quick_toggle_theme(self) -> None:
        target_mode = "light" if self._dark else "dark"
        self._apply_live_theme_mode(target_mode, show_toast=True)

    def _on_theme_mode_selected(self, mode: str) -> None:
        self._apply_live_theme_mode(mode, show_toast=False)

    def _apply_live_theme_mode(self, mode: str, show_toast: bool = False) -> None:
        cur_tab = self._seg.currentIndex() if hasattr(self, "_seg") else 0
        self._collect_config()
        norm = theme.set_theme_mode(mode)
        self._cfg["style"]["themeMode"] = norm
        new_dark = theme.is_system_dark()
        if new_dark != self._dark:
            self._dark = new_dark
            self.setStyleSheet(theme.settings_qss(self._dark, self._metrics.cb_ind, self._scale))
            try:
                hwnd = int(self.winId())
                if hwnd:
                    glass.style_titlebar(hwnd, self._dark)
            except Exception:
                pass
            self._rebuild_ui()
            self._load()
            self._connect_preview()
            self._seg.setCurrentIndex(cur_tab, notify=False)
            self._stack.setCurrentIndex(cur_tab)
            if self._toast is not None:
                self._toast.set_dark_scale(self._dark, self._scale)
                self._toast.raise_()
        else:
            self._appearance_page.sync_theme_mode_selection(norm)
        self._on_preview()
        if show_toast:
            label = {"auto": "跟随系统", "light": "浅色模式", "dark": "深色模式"}.get(norm, norm)
            self._show_toast(f"已切换至{label}", kind="info")

    # ── 底部操作栏动作 ──────────────────────────────────────────────────────

    def _on_restore(self) -> None:
        cur_tab = self._seg.currentIndex() if hasattr(self, "_seg") else 0
        self._cfg = copy.deepcopy(config_mod.DEFAULT_CONFIG)
        theme.apply_theme_mode_from_cfg(self._cfg)
        new_dark = theme.is_system_dark()
        if new_dark != self._dark:
            self._dark = new_dark
            self.setStyleSheet(theme.settings_qss(self._dark, self._metrics.cb_ind, self._scale))
            try:
                hwnd = int(self.winId())
                if hwnd:
                    glass.style_titlebar(hwnd, self._dark)
            except Exception:
                pass
            self._rebuild_ui()
            self._load()
            self._connect_preview()
            self._seg.setCurrentIndex(cur_tab, notify=False)
            self._stack.setCurrentIndex(cur_tab)
            if self._toast is not None:
                self._toast.set_dark_scale(self._dark, self._scale)
                self._toast.raise_()
        else:
            self._load()
        self._on_preview()
        self._show_toast("已恢复默认配置（点应用或保存生效）", kind="info")

    def _apply_page_side_effects(self) -> None:
        for page in self._pages:
            page.apply_side_effects()

    def _on_apply(self) -> None:
        self._collect_config()
        self._apply_page_side_effects()
        config_mod.save_config(self._cfg)
        self._snapshot = copy.deepcopy(self._cfg)
        if self._preview_callback:
            self._preview_callback(self._cfg)
        self._show_toast("设置已应用并保存", kind="ok")

    def _on_save(self) -> None:
        self._collect_config()
        self._apply_page_side_effects()
        config_mod.save_config(self._cfg)
        self.accept()

    def _on_cancel(self) -> None:
        theme.apply_theme_mode_from_cfg(self._snapshot)
        if self._preview_callback:
            self._preview_callback(self._snapshot)
        self.reject()

    def get_config(self) -> dict[str, Any]:
        return self._cfg

    # ── 算力同步异步信号路由 ────────────────────────────────────────────────

    def _on_quota_rows_updated(self, updates: Any) -> None:
        self._extensions_page.on_sync_rows_updated(updates)

    def _on_quota_test_done(self, txt: str) -> None:
        self._extensions_page.on_sync_finished(txt)

    # ── 面向测试与调用方的薄属性委托 ────────────────────────────────────────

    @property
    def _sched_rows(self):
        return self._schedule_page.rows

    @property
    def _default_edit(self):
        return self._schedule_page.default_edit

    @property
    def _todo_rows(self):
        return self._todo_page.rows

    @property
    def _display_mode_combo(self):
        return self._bar_style_page.display_mode_combo

    @property
    def _capsule_left_combo(self):
        return self._bar_style_page.capsule_left_combo

    @property
    def _capsule_right_combo(self):
        return self._bar_style_page.capsule_right_combo

    @property
    def _color_buttons(self):
        return self._bar_style_page.color_buttons

    @property
    def _theme_mode_seg(self):
        return self._appearance_page.theme_mode_seg

    @property
    def _panel_card_items(self):
        return self._appearance_page.panel_card_items

    @_panel_card_items.setter
    def _panel_card_items(self, items):
        self._appearance_page.panel_card_items = items

    def _refresh_panel_cards_ui(self) -> None:
        self._appearance_page.refresh_ui()

    def _reset_panel_cards_to_default(self) -> None:
        self._appearance_page.reset_to_default()

    @property
    def _quota_rows(self):
        return self._extensions_page.rows

    @_quota_rows.setter
    def _quota_rows(self, rows):
        self._extensions_page.rows = rows

    def _on_click_add_quota(self) -> None:
        self._extensions_page.on_click_add()

    def _on_edit_quota_row(self, entry: dict[str, Any]) -> None:
        self._extensions_page.on_edit_row(entry)

    @property
    def _source_widgets(self):
        return self._plugins_page.source_widgets

    @staticmethod
    def _norm_time(text, allow_empty: bool = True, default_str: str = ""):
        return normalize_time_str(text, allow_empty=allow_empty, default_str=default_str)
