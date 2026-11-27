"""app/gui/settings/pages/plugins_page.py — 设置中心「扩展插件」页"""

from __future__ import annotations

import os
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QLineEdit, QSpinBox, QWidget

from app.core import sources
from app.gui import widgets as ui_parts
from app.styles import tokens

from ..form_helpers import SettingsFormContext
from .base import BaseSettingsPage


class PluginsPage(BaseSettingsPage):
    """数据源插件开关、刷新周期及专属参数（天气城市、Git 仓库目录）配置页。"""

    page_id = "plugins"
    title = "扩展插件"

    def __init__(self) -> None:
        super().__init__()
        self.source_widgets: dict[str, dict[str, Any]] = {}

    def build(self, ctx: SettingsFormContext) -> QWidget:
        self._ctx = ctx
        self.source_widgets = {}
        m = ctx.metrics
        t = tokens.get_tokens(ctx.dark)
        page, lay = ctx.make_scroll_page()

        open_dir_btn = ctx.make_action_btn("打开本地插件目录", "folder")
        open_dir_btn.setFixedHeight(ctx.px(30))
        open_dir_btn.clicked.connect(self._on_open_user_plugins_folder)

        g_intro = ui_parts.SettingGroupCard(
            ctx.dark,
            ctx.scale,
            title="数据源与功能扩展 (Plugins)",
            icon_name="plugin",
            header_right=open_dir_btn,
        )
        tip_p = ctx.make_tip(
            "支持在 %APPDATA%/AnyBar/plugins/ 中编写自定义 Python 脚本扩展数据源，开启后可在任务栏右键切换展示。"
        )
        tip_p.setContentsMargins(0, ctx.px(6), 0, ctx.px(2))
        g_intro.add_row(tip_p, divider=False)
        lay.addWidget(g_intro)

        ext_sources = [
            r
            for r in sources.list_sources()
            if r.info.id != "quota" and not r.info.id.endswith("_quota")
        ]

        src_icons = {
            "system": ("cpu", t.info),
            "weather": ("weather", t.info),
            "dev": ("git", t.ok_solid),
        }

        if not ext_sources:
            empty_g = ui_parts.SettingGroupCard(ctx.dark, ctx.scale)
            empty_g.add_setting_row("暂无已安装的扩展插件", [])
            lay.addWidget(empty_g)
        else:
            for reg in ext_sources:
                ic_name, _ic_col = src_icons.get(reg.info.id, ("plugin", t.accent))
                s_check = ui_parts.ToggleSwitch("启用", ctx.dark, ctx.scale)
                card = ui_parts.SettingGroupCard(
                    ctx.dark,
                    ctx.scale,
                    title=reg.info.title,
                    icon_name=ic_name,
                    header_right=s_check,
                )

                s_spin = QSpinBox()
                s_spin.setRange(reg.info.min_interval_sec, 3600)
                s_spin.setSuffix(" 秒")
                s_spin.setFixedWidth(ctx.px(84))
                s_spin.setFixedHeight(m.edit_h)
                s_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)

                desc = getattr(reg.info, "description", "") or ""
                card.add_setting_row("刷新间隔", [s_spin], desc=desc)
                w_dict: dict[str, Any] = {"enabled": s_check, "interval": s_spin}

                if reg.info.id == "weather":
                    c_edit = QLineEdit()
                    c_edit.setPlaceholderText("留空自动按 IP 定位，或输入城市如：北京、上海、武汉")
                    c_edit.setFixedHeight(m.edit_h)
                    c_edit.setMinimumWidth(ctx.px(260))
                    card.add_setting_row("目标城市", [c_edit])
                    w_dict["city"] = c_edit

                if reg.info.id == "dev":
                    r_edit = QLineEdit()
                    r_edit.setPlaceholderText("留空自动检测当前工作目录")
                    r_edit.setFixedHeight(m.edit_h)
                    r_edit.setMinimumWidth(ctx.px(220))
                    r_browse = ctx.make_action_btn("浏览...", "folder")
                    r_browse.setFixedHeight(m.edit_h)

                    def _choose_dev_dir(edit=r_edit):
                        p = QFileDialog.getExistingDirectory(
                            ctx.dialog,
                            "选择要监控的 Git 仓库目录",
                            edit.text().strip() or os.getcwd(),
                        )
                        if p:
                            edit.setText(p)

                    r_browse.clicked.connect(_choose_dev_dir)
                    card.add_setting_row("仓库目录", [r_edit, r_browse])
                    w_dict["repoPath"] = r_edit

                lay.addWidget(card)
                self.source_widgets[reg.info.id] = w_dict

        g_dev = ui_parts.SettingGroupCard(
            ctx.dark, ctx.scale, title="自定义插件开发", icon_name="terminal"
        )
        dev_tip = ctx.make_tip(
            "AnyBar 提供开放标准数据源接口，在 app/core/sources/ 编写单文件即可自动注册并在任务栏与浮窗展示。详见 CONTRIBUTING.md。"
        )
        dev_tip.setContentsMargins(0, ctx.px(6), 0, ctx.px(2))
        g_dev.add_row(dev_tip, divider=False)
        lay.addWidget(g_dev)

        lay.addStretch(1)
        return page

    @staticmethod
    def _on_open_user_plugins_folder() -> None:
        p = sources.get_user_plugins_dir()
        p.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def load(self, cfg: dict[str, Any]) -> None:
        src_cfg = cfg.get("sources") or {}
        for s_id, s_w in self.source_widgets.items():
            conf = src_cfg.get(s_id) or {}
            reg = sources.get_source(s_id)
            default_sec = reg.info.default_interval_sec if reg else 60
            s_w["enabled"].setChecked(bool(conf.get("enabled", True)))
            s_w["interval"].setValue(int(conf.get("intervalSec", default_sec)))
            if "city" in s_w:
                s_w["city"].setText(str(conf.get("city", "") or ""))
            if "repoPath" in s_w:
                s_w["repoPath"].setText(str(conf.get("repoPath", "") or ""))

    def collect(self, cfg: dict[str, Any]) -> None:
        sources_cfg = cfg.setdefault("sources", {})
        for s_id, s_w in self.source_widgets.items():
            entry: dict[str, Any] = {
                "enabled": s_w["enabled"].isChecked(),
                "intervalSec": s_w["interval"].value(),
            }
            if "city" in s_w:
                entry["city"] = s_w["city"].text().strip()
            if "repoPath" in s_w:
                entry["repoPath"] = s_w["repoPath"].text().strip()
            sources_cfg[s_id] = entry

    def connect_preview(self) -> None:
        if self._ctx is None:
            return
        for s_w in self.source_widgets.values():
            s_w["enabled"].stateChanged.connect(self._ctx.schedule_preview)
            s_w["interval"].valueChanged.connect(self._ctx.schedule_preview)
            if "city" in s_w:
                s_w["city"].editingFinished.connect(self._ctx.schedule_preview)
