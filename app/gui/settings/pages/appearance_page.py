"""app/gui/settings/pages/appearance_page.py — 设置中心「界面与浮窗」页（全局主题 / 开机自启 / 悬浮窗卡片排序）"""

from __future__ import annotations

import copy
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.core import config as config_mod
from app.gui import widgets as ui_parts
from app.platform import autostart
from app.styles import icons, qss_engine, theme, tokens

from ..form_helpers import SettingsFormContext
from .base import BaseSettingsPage

THEME_MODE_KEYS = ("auto", "light", "dark")


class AppearancePage(BaseSettingsPage):
    """全局深浅主题、Windows 开机自启与悬浮窗卡片拖拽排序/显隐配置页。"""

    page_id = "appearance"
    title = "界面与浮窗"

    def __init__(self, on_theme_mode_selected: Callable[[str], None]) -> None:
        super().__init__()
        self._on_theme_mode_selected = on_theme_mode_selected
        self.theme_mode_keys = THEME_MODE_KEYS
        self.theme_mode_seg: ui_parts.SlidingSegmentedControl | None = None
        self.autostart_check: ui_parts.ToggleSwitch | None = None
        self.panel_cards_container: ui_parts.AnimatedReorderContainer | None = None
        self.panel_card_items: list[dict[str, Any]] = []
        self._panel_card_entries: list[dict[str, Any]] = []

    def build(self, ctx: SettingsFormContext) -> QWidget:
        self._ctx = ctx
        self._panel_card_entries = []
        m = ctx.metrics
        page, lay = ctx.make_scroll_page()

        # 1. 全局外观与系统启动
        g_global = ui_parts.SettingGroupCard(
            ctx.dark, ctx.scale, title="全局外观与启动", icon_name="theme"
        )

        self.theme_mode_seg = ui_parts.SlidingSegmentedControl(
            ["跟随系统", "浅色", "深色"],
            ctx.dark,
            font=ctx.dialog.font(),
            scale=ctx.scale,
            height_log=32.0,
            min_width_log=228.0,
        )
        g_global.add_setting_row(
            "界面主题",
            [self.theme_mode_seg],
            desc="切换整个软件（常驻条、悬浮窗与设置中心）的深浅色外观",
        )

        self.autostart_check = ui_parts.ToggleSwitch("随 Windows 登录自动启动", ctx.dark, ctx.scale)
        g_global.add_setting_row("开机自启动", [self.autostart_check])
        lay.addWidget(g_global)

        # 2. 悬浮窗卡片定制与拖拽排序
        reset_cards_btn = ctx.make_action_btn("恢复默认顺序", "reset")
        reset_cards_btn.setFixedHeight(ctx.px(30))
        reset_cards_btn.clicked.connect(self.reset_to_default)

        g_cards_hdr = ui_parts.SettingGroupCard(
            ctx.dark,
            ctx.scale,
            title="悬浮窗卡片定制与排序",
            icon_name="layers",
            header_right=reset_cards_btn,
        )
        tip_w = ctx.make_tip(
            "开启或关闭右侧开关控制卡片显隐；按住每张卡片左侧 ≡ 抓手上下拖拽即可实时排序。"
        )
        tip_w.setContentsMargins(0, ctx.px(6), 0, ctx.px(2))
        g_cards_hdr.add_row(tip_w, divider=False)
        lay.addWidget(g_cards_hdr)

        self.panel_cards_container = ui_parts.AnimatedReorderContainer(
            row_h=m.panel_row_h,
            spacing=ctx.px(8),
            dark=ctx.dark,
            scale=ctx.scale,
        )
        self.panel_cards_container.orderChanged.connect(self._on_order_changed)
        lay.addWidget(self.panel_cards_container)
        lay.addStretch(1)
        return page

    def reset_to_default(self) -> None:
        self.panel_card_items = copy.deepcopy(config_mod.DEFAULT_PANEL_CARDS)
        self.refresh_ui()
        if self._ctx is not None:
            self._ctx.schedule_preview()
            self._ctx.show_toast("已恢复默认悬浮窗卡片顺序", "info")

    def refresh_ui(self) -> None:
        if self._ctx is None or self.panel_cards_container is None:
            return
        ctx = self._ctx
        m = ctx.metrics
        container = self.panel_cards_container
        container.clear_cards()

        t = tokens.get_tokens(ctx.dark)
        card_icon_map = {
            "schedule": ("schedule", t.warn_solid),
            "todos": ("todo", t.accent),
            "system": ("cpu", t.info),
            "quotas": ("spark", t.violet),
            "weather": ("weather", t.info),
            "dev": ("git", t.ok_solid),
        }

        self._panel_card_entries = []
        for item in self.panel_card_items:
            cid = item.get("id", "")
            ic_name, ic_color = card_icon_map.get(cid, ("layers", t.accent))
            name = item.get("name") or cid
            desc = item.get("desc") or ""
            is_on = bool(item.get("enabled", True))

            card, h = ctx.make_row_card(height=m.panel_row_h)
            h.setContentsMargins(ctx.px(10), ctx.px(6), ctx.px(14), ctx.px(6))
            h.setSpacing(ctx.px(10))

            handle = ui_parts.ReorderHandle(card, container, dark=ctx.dark, scale=ctx.scale)
            handle.setFixedSize(m.handle_w, ctx.px(40))
            h.addWidget(handle, 0, Qt.AlignmentFlag.AlignVCenter)

            ic_w = icons.IconWidget(ic_name, ic_color if is_on else t.text_disabled, size=ctx.px(16))
            h.addWidget(ic_w, 0, Qt.AlignmentFlag.AlignVCenter)

            v_text = QVBoxLayout()
            v_text.setContentsMargins(0, 0, 0, 0)
            v_text.setSpacing(ctx.px(2))
            v_text.addStretch(1)

            lbl_title = QLabel(name)
            lbl_title.setFont(theme.ui_font(12.5 * ctx.scale, 600))
            qss_engine.set_role(lbl_title, "primary" if is_on else "muted", polish=False)
            v_text.addWidget(lbl_title)

            if desc:
                lbl_desc = QLabel(desc)
                lbl_desc.setFont(theme.ui_font(11 * ctx.scale, 400))
                qss_engine.set_role(lbl_desc, "muted", polish=False)
                v_text.addWidget(lbl_desc)

            v_text.addStretch(1)
            h.addLayout(v_text, 1)

            sw = ui_parts.ToggleSwitch("", ctx.dark, ctx.scale)
            sw.setChecked(is_on)
            h.addWidget(sw, 0, Qt.AlignmentFlag.AlignVCenter)

            def _bind_toggle(cur_item, cur_title_lbl, cur_ic, active_ic_col):
                def _do_toggle(checked: bool):
                    cur_item["enabled"] = bool(checked)
                    qss_engine.set_role(cur_title_lbl, "primary" if checked else "muted", polish=True)
                    cur_ic.set_color(active_ic_col if checked else t.text_disabled)
                    ctx.schedule_preview()
                return _do_toggle

            sw.toggled.connect(_bind_toggle(item, lbl_title, ic_w, ic_color))
            self._panel_card_entries.append({"item": item, "card": card})
            container.add_card(card)

    def _on_order_changed(self) -> None:
        if self.panel_cards_container is None or not self._panel_card_entries:
            return
        item_of = {e["card"]: e["item"] for e in self._panel_card_entries}
        entry_of = {e["card"]: e for e in self._panel_card_entries}
        ordered_items, ordered_entries = [], []
        for c in self.panel_cards_container.cards():
            if c in item_of:
                ordered_items.append(item_of[c])
                ordered_entries.append(entry_of[c])
        for e in self._panel_card_entries:
            if e not in ordered_entries:
                ordered_items.append(e["item"])
                ordered_entries.append(e)
        self.panel_card_items = ordered_items
        self._panel_card_entries = ordered_entries
        if self._ctx is not None:
            self._ctx.schedule_preview()

    def sync_theme_mode_selection(self, mode: str) -> None:
        if self.theme_mode_seg is not None:
            tm_idx = THEME_MODE_KEYS.index(mode) if mode in THEME_MODE_KEYS else 0
            self.theme_mode_seg.setCurrentIndex(tm_idx, notify=False)

    def load(self, cfg: dict[str, Any]) -> None:
        style = cfg.get("style") or {}
        cur_tm = str(style.get("themeMode", "auto") or "auto")
        self.sync_theme_mode_selection(cur_tm)

        if self.autostart_check is not None:
            self.autostart_check.setChecked(autostart.is_enabled())

        panel_cards = cfg.get("panelCards")
        if isinstance(panel_cards, list) and panel_cards:
            self.panel_card_items = copy.deepcopy(panel_cards)
        else:
            self.panel_card_items = copy.deepcopy(config_mod.DEFAULT_PANEL_CARDS)
        self.refresh_ui()

    def collect(self, cfg: dict[str, Any]) -> None:
        style = cfg.setdefault("style", {})
        if self.theme_mode_seg is not None:
            tm_idx = self.theme_mode_seg.currentIndex()
            if 0 <= tm_idx < len(THEME_MODE_KEYS):
                style["themeMode"] = THEME_MODE_KEYS[tm_idx]
        cfg["panelCards"] = copy.deepcopy(self.panel_card_items)

    def connect_preview(self) -> None:
        if self.theme_mode_seg is not None:
            self.theme_mode_seg.currentChanged.connect(self._handle_seg_changed)

    def _handle_seg_changed(self, idx: int) -> None:
        if 0 <= idx < len(THEME_MODE_KEYS):
            self._on_theme_mode_selected(THEME_MODE_KEYS[idx])

    def apply_side_effects(self) -> None:
        if self.autostart_check is None:
            return
        if self.autostart_check.isChecked():
            autostart.enable()
        else:
            autostart.disable()

    def on_scale_changed(self, dark: bool, scale: float) -> None:
        if self.panel_cards_container is not None and self._ctx is not None:
            self.panel_cards_container.set_dark_scale(
                dark, scale, self._ctx.metrics.panel_row_h, self._ctx.px(8)
            )
