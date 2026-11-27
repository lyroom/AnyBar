"""app/gui/settings/pages/extensions_page.py — 设置中心「算力套餐」页"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QWidget,
)

from app.core import quota_api
from app.gui import widgets as ui_parts
from app.styles import qss_engine, theme

from ..coding_plan_dialog import CodingPlanDialog
from ..form_helpers import SettingsFormContext, fmt_quota_num, set_edit_text
from ..quota_controller import QuotaSyncController, discover_local_quota_candidates
from .base import BaseSettingsPage


class ExtensionsPage(BaseSettingsPage):
    """算力套餐监控开关、自动发现、异步刷新测试与拖拽排序管理页。"""

    page_id = "extensions"
    title = "算力套餐"

    def __init__(self, sync_controller: QuotaSyncController) -> None:
        super().__init__()
        self._sync_ctrl = sync_controller
        self.rows: list[dict[str, Any]] = []
        self._prev_quota_api: dict[str, Any] = {}
        self._quota_enable: ui_parts.ToggleSwitch | None = None
        self._quota_interval: QSpinBox | None = None
        self._discover_btn: QPushButton | None = None
        self._test_btn: QPushButton | None = None
        self._status_lbl: QLabel | None = None
        self._container: ui_parts.AnimatedReorderContainer | None = None

    def build(self, ctx: SettingsFormContext) -> QWidget:
        self._ctx = ctx
        self.rows = []
        m = ctx.metrics
        page, lay = ctx.make_scroll_page()

        self._quota_enable = ui_parts.ToggleSwitch("实时同步", ctx.dark, ctx.scale)
        self._quota_interval = QSpinBox()
        self._quota_interval.setRange(1, 360)
        self._quota_interval.setSuffix(" 分")
        self._quota_interval.setFixedWidth(ctx.px(74))
        self._quota_interval.setFixedHeight(m.edit_h)
        self._quota_interval.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._discover_btn = ctx.make_action_btn("扫描导入本机套餐", "bolt")
        self._discover_btn.setFixedHeight(m.edit_h)
        self._discover_btn.clicked.connect(self.on_discover)

        self._test_btn = ctx.make_action_btn("立即刷新验证", "refresh")
        self._test_btn.setFixedHeight(m.edit_h)
        self._test_btn.clicked.connect(self.on_sync_test)

        g_quota = ui_parts.SettingGroupCard(
            ctx.dark, ctx.scale, title="算力监控与同步", icon_name="spark"
        )
        g_quota.add_setting_row(
            "监控选项",
            [
                self._quota_enable,
                ctx.make_muted_label("间隔"),
                self._quota_interval,
            ],
        )
        g_quota.add_setting_row(
            "快捷操作",
            [self._discover_btn, self._test_btn],
        )
        lay.addWidget(g_quota)

        self._status_lbl = QLabel()
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setContentsMargins(ctx.px(4), 0, ctx.px(4), 0)
        self._status_lbl.setFont(theme.ui_font(11.5 * ctx.scale, 500))
        self._set_status_text(
            "下方列表即为任务栏进度条与悬停面板的唯一数据源（所见即所得）；点「扫描导入本机套餐」可一键导入。"
        )
        lay.addWidget(self._status_lbl)

        lay.addWidget(ctx.make_col_header([
            ("排序", m.handle_w, 0, Qt.AlignmentFlag.AlignCenter),
            ("渠道类型", m.quota_prov_w, 0, Qt.AlignmentFlag.AlignCenter),
            ("显示名称", m.quota_name_w, 0),
            ("连接凭证", None, 1, Qt.AlignmentFlag.AlignLeft, m.quota_key_min_w),
            ("当前/余额", m.quota_val_w, 0, Qt.AlignmentFlag.AlignCenter),
            ("", ctx.px(6), 0),
            ("上限", m.quota_val_w, 0, Qt.AlignmentFlag.AlignCenter),
            ("单位", m.unit_w, 0, Qt.AlignmentFlag.AlignCenter),
            ("编辑", m.del_w, 0, Qt.AlignmentFlag.AlignCenter),
            ("删除", m.del_w, 0, Qt.AlignmentFlag.AlignCenter),
        ]))

        self._container = ui_parts.AnimatedReorderContainer(
            row_h=m.row_h,
            spacing=ctx.px(6),
            dark=ctx.dark,
            scale=ctx.scale,
        )
        self._container.orderChanged.connect(self._on_order_changed)
        lay.addWidget(self._container)

        lay.addWidget(ctx.make_add_btn(
            "+ 添加算力套餐（配置 Coding Plan 直连或 Magpie 聚合同步）",
            self.on_click_add,
        ))
        lay.addWidget(ctx.make_tip(
            "列表前 4 项展示在任务栏进度条（支持拖拽排序）；自动渠道按间隔同步，手动渠道按输入展示。",
            icon_name="info",
        ))
        lay.addWidget(ctx.make_tip(
            "本地安全：API Key 经 Windows DPAPI 强加密落盘；直连官方 API，零中转零遥测。",
            icon_name="shield",
        ))
        lay.addStretch(1)
        return page

    def _set_status_text(self, txt: str, err: bool = False) -> None:
        if self._status_lbl is None:
            return
        self._status_lbl.setText(txt)
        if err:
            role = "danger"
        elif txt.startswith("✓"):
            role = "ok"
        else:
            role = "muted"
        qss_engine.set_role(self._status_lbl, role, polish=True)

    def add_row(self) -> dict[str, Any]:
        assert self._ctx is not None and self._container is not None
        ctx = self._ctx
        m = ctx.metrics

        provider = QComboBox()
        for p_id, p_label in quota_api.PROVIDER_TYPES:
            provider.addItem(p_label, p_id)
        provider.setFixedWidth(m.quota_prov_w)
        provider.setFixedHeight(m.edit_h)
        ctx.style_combo_palette(provider)

        name = QLineEdit("")
        name.setPlaceholderText("显示名称")
        name.setFixedWidth(m.quota_name_w)
        name.setFixedHeight(m.edit_h)

        api_key = QLineEdit("")
        api_key.setPlaceholderText("平台标识 (如 zcode / codex)")
        api_key.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        api_key.setMinimumWidth(m.quota_key_min_w)
        api_key.setFixedHeight(m.edit_h)

        value = QLineEdit("")
        value.setPlaceholderText("自动")
        value.setFixedWidth(m.quota_val_w)
        value.setFixedHeight(m.edit_h)
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value.setFont(theme.ui_font(12 * ctx.scale, 500, mono=True))

        slash = QLabel("/")
        slash.setFixedWidth(ctx.px(6))
        slash.setAlignment(Qt.AlignmentFlag.AlignCenter)

        limit = QLineEdit("")
        limit.setPlaceholderText("上限")
        limit.setFixedWidth(m.quota_val_w)
        limit.setFixedHeight(m.edit_h)
        limit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        limit.setFont(theme.ui_font(12 * ctx.scale, 500, mono=True))

        unit = QLineEdit("")
        unit.setPlaceholderText("单位")
        unit.setFixedWidth(m.unit_w)
        unit.setFixedHeight(m.edit_h)
        unit.setAlignment(Qt.AlignmentFlag.AlignCenter)

        entry: dict[str, Any] = {
            "provider": provider,
            "name": name,
            "apiKey": api_key,
            "value": value,
            "limit": limit,
            "unit": unit,
        }
        provider.currentIndexChanged.connect(lambda _idx=0, e=entry: self._sync_row_mode(e))
        self._sync_row_mode(entry)

        card, h = ctx.make_row_card()
        handle = ui_parts.ReorderHandle(card, self._container, dark=ctx.dark, scale=ctx.scale)
        handle.setFixedSize(m.handle_w, m.edit_h)
        h.addWidget(handle)
        h.addWidget(provider)
        h.addWidget(name)
        h.addWidget(api_key, 1)
        h.addWidget(value)
        h.addWidget(slash)
        h.addWidget(limit)
        h.addWidget(unit)
        edit_btn = ctx.make_edit_btn(lambda _c=False, e=entry: self.on_edit_row(e))
        h.addWidget(edit_btn)
        trash = ctx.make_del_btn(
            lambda _checked=False, e=entry: ctx.remove_row(self.rows, e, self._container)
        )
        h.addWidget(trash)

        entry["card"] = card
        entry["handle"] = handle
        self.rows.append(entry)
        handle.set_card_and_container(card, self._container)
        self._container.add_card(card)

        for w in (name, value, limit, unit):
            w.textChanged.connect(ctx.schedule_preview)
        provider.currentIndexChanged.connect(ctx.schedule_preview)

        orig_dbl = card.mouseDoubleClickEvent

        def on_dbl_click(event, e=entry):
            self.on_edit_row(e)
            if orig_dbl:
                orig_dbl(event)

        card.mouseDoubleClickEvent = on_dbl_click
        return entry

    def _sync_row_mode(self, entry: dict[str, Any]) -> None:
        prov = str(entry["provider"].currentData() or "manual")
        key_edit = entry["apiKey"]
        val_edit = entry["value"]
        lim_edit = entry["limit"]
        unit_edit = entry["unit"]
        name_edit = entry["name"]

        if prov == "manual":
            key_edit.setEnabled(False)
            key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            key_edit.setPlaceholderText("手动模式无需凭证")
            val_edit.setPlaceholderText("用量/余额")
            lim_edit.setPlaceholderText("上限")
            unit_edit.setPlaceholderText("单位")
        elif prov == "magpie":
            key_edit.setEnabled(True)
            key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            key_edit.setPlaceholderText("平台标识 (如 zcode / codex / codearts)")
            val_edit.setPlaceholderText("自动同步")
            lim_edit.setPlaceholderText("100")
            unit_edit.setPlaceholderText("%")
        elif prov == "codex":
            key_edit.setEnabled(True)
            key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            key_edit.setPlaceholderText("留空自动读本机 ~/.codex 或填 Token")
            val_edit.setPlaceholderText("自动同步")
            lim_edit.setPlaceholderText("100")
            unit_edit.setPlaceholderText("%")
            if not name_edit.text().strip():
                name_edit.setText("Codex")
        elif prov in ("claude", "anthropic"):
            key_edit.setEnabled(True)
            key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            key_edit.setPlaceholderText("留空读本机 ~/.claude.json 或填 API Key")
            val_edit.setPlaceholderText("自动同步")
            lim_edit.setPlaceholderText("100")
            unit_edit.setPlaceholderText("%")
            if not name_edit.text().strip():
                name_edit.setText("Claude")
        elif prov == "cursor":
            key_edit.setEnabled(True)
            key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            key_edit.setPlaceholderText("留空读本机 Cursor 或填 Session Token")
            val_edit.setPlaceholderText("自动同步")
            lim_edit.setPlaceholderText("500")
            unit_edit.setPlaceholderText("req")
            if not name_edit.text().strip():
                name_edit.setText("Cursor")
        elif prov == "openai":
            key_edit.setEnabled(True)
            key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            key_edit.setPlaceholderText("填写 OpenAI API Key (sk-...)")
            val_edit.setPlaceholderText("自动同步")
            lim_edit.setPlaceholderText("100")
            unit_edit.setPlaceholderText("USD")
            if not name_edit.text().strip():
                name_edit.setText("OpenAI")
        else:
            key_edit.setEnabled(True)
            key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            key_edit.setPlaceholderText(f"填写 {prov.upper()} API Key")
            val_edit.setPlaceholderText("自动同步")
            default_names = {
                "deepseek": "DeepSeek",
                "glm": "GLM",
                "claude": "Claude",
                "cursor": "Cursor",
                "openai": "OpenAI",
                "kimi": "Kimi",
                "openrouter": "OpenRouter",
                "newapi": "NewAPI",
            }
            if not name_edit.text().strip() and prov in default_names:
                name_edit.setText(default_names[prov])

    def _apply_data_to_row(self, entry: dict[str, Any], data: dict[str, Any]) -> None:
        prov = str(data.get("provider") or "manual").lower()
        p_idx = entry["provider"].findData(prov)
        if p_idx >= 0:
            entry["provider"].setCurrentIndex(p_idx)
        else:
            entry["provider"].setEditText(prov)

        if data.get("name"):
            set_edit_text(entry["name"], str(data["name"]))
        if "apiKey" in data:
            set_edit_text(entry["apiKey"], str(data["apiKey"]))
        if "baseUrl" in data:
            entry["baseUrl"] = str(data["baseUrl"])

        if data.get("used") is not None and data.get("limit") is not None:
            set_edit_text(entry["value"], fmt_quota_num(data["used"]))
            set_edit_text(entry["limit"], fmt_quota_num(data["limit"]))
            if data.get("unit"):
                set_edit_text(entry["unit"], str(data["unit"]))
        elif data.get("balance"):
            set_edit_text(entry["value"], str(data["balance"]))
        self._sync_row_mode(entry)

    def on_click_add(self) -> None:
        if self._ctx is None:
            return
        ctx = self._ctx
        dlg = CodingPlanDialog(ctx.dialog, item_data=None, dark=ctx.dark, scale=ctx.scale)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_data = dlg.get_data()
            entry = self.add_row()
            self._apply_data_to_row(entry, new_data)
            ctx.schedule_preview()
            msg = f"✓ 已添加 {new_data.get('name', '套餐')}，点「保存并关闭」生效"
            self._set_status_text(msg)
            ctx.show_toast(msg, "ok")
        dlg.deleteLater()

    def on_edit_row(self, entry: dict[str, Any]) -> None:
        if self._ctx is None:
            return
        ctx = self._ctx
        item_data = {
            "name": entry["name"].text().strip(),
            "provider": str(entry["provider"].currentData() or "manual"),
            "apiKey": entry["apiKey"].text().strip(),
            "value": entry["value"].text().strip(),
            "limit": entry["limit"].text().strip(),
            "unit": entry["unit"].text().strip(),
            "baseUrl": entry.get("baseUrl", ""),
            "color": entry.get("color", ""),
        }
        dlg = CodingPlanDialog(ctx.dialog, item_data=item_data, dark=ctx.dark, scale=ctx.scale)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_data = dlg.get_data()
            self._apply_data_to_row(entry, new_data)
            ctx.schedule_preview()
            msg = f"✓ 已更新 {new_data.get('name', '套餐')}，点「保存并关闭」生效"
            self._set_status_text(msg)
            ctx.show_toast(msg, "ok")
        dlg.deleteLater()

    def _on_order_changed(self) -> None:
        if self._container is None:
            return
        card_map = {e.get("card"): e for e in self.rows if e.get("card") is not None}
        ordered = [card_map[c] for c in self._container.cards() if c in card_map]
        for e in self.rows:
            if e not in ordered:
                ordered.append(e)
        self.rows = ordered
        if self._ctx is not None:
            self._ctx.schedule_preview()

    def _populate_initial_rows(self, qa: dict[str, Any]) -> None:
        mp_provs = qa.get("magpieProviders") or []
        if str(qa.get("source", "")) == "magpie" or mp_provs:
            try:
                cards = quota_api.fetch_magpie_quotas(
                    "http://127.0.0.1:3425",
                    providers_filter=mp_provs or None,
                )
                if isinstance(cards, dict):
                    cards = cards.get("cards") or []
                for c in cards[:4]:
                    entry = self.add_row()
                    p_idx = entry["provider"].findData("magpie")
                    entry["provider"].setCurrentIndex(p_idx if p_idx >= 0 else 0)
                    set_edit_text(entry["name"], str(c.get("title") or c.get("name") or c.get("provider")))
                    set_edit_text(entry["apiKey"], str(c.get("provider") or ""))
                    w = quota_api.primary_window(c.get("windows"))
                    if w and w.get("percent") is not None:
                        set_edit_text(entry["value"], fmt_quota_num(round(float(w["percent"]), 1)))
                        set_edit_text(entry["limit"], "100")
                        set_edit_text(entry["unit"], "%")
                    self._sync_row_mode(entry)
                if self.rows:
                    return
            except Exception:
                pass
        old_key = str(qa.get("apiKey", "")).strip()
        if old_key:
            entry = self.add_row()
            p_idx = entry["provider"].findData("glm")
            entry["provider"].setCurrentIndex(p_idx if p_idx >= 0 else 0)
            set_edit_text(entry["name"], "GLM")
            set_edit_text(entry["apiKey"], old_key)
            self._sync_row_mode(entry)

    def on_discover(self) -> None:
        if self._ctx is None:
            return
        ctx = self._ctx
        added: list[str] = []
        candidates = discover_local_quota_candidates()

        for cand in candidates:
            prov = str(cand.get("provider") or "").lower()
            name = str(cand.get("name") or prov)
            key = str(cand.get("apiKey") or "")
            label = str(cand.get("label") or name)

            if prov == "magpie":
                if any(
                    str(e["provider"].currentData() or "").lower() == "magpie"
                    and e["apiKey"].text().strip().lower() == key.lower()
                    for e in self.rows
                ):
                    continue
                entry = self.add_row()
                self._apply_data_to_row(entry, cand)
                added.append(label)
                continue

            match_provs = ("claude", "anthropic") if prov == "claude" else (prov,)
            if any(str(e["provider"].currentData() or "").lower() in match_provs for e in self.rows):
                continue

            target = next(
                (
                    e
                    for e in self.rows
                    if e["name"].text().strip().lower() in match_provs
                    and str(e["provider"].currentData() or "") == "manual"
                ),
                None,
            )
            if target is None:
                target = self.add_row()
            p_idx = target["provider"].findData(prov)
            target["provider"].setCurrentIndex(p_idx if p_idx >= 0 else 0)
            set_edit_text(target["name"], name)
            set_edit_text(target["apiKey"], key)
            self._sync_row_mode(target)
            added.append(label)

        if added:
            msg = f"✓ 已自动发现并导入 {len(added)} 个本机套餐（{' / '.join(added)}）"
            self._set_status_text(msg)
            ctx.show_toast(msg, "ok")
            ctx.schedule_preview()
            self.on_sync_test()
        elif self.rows and any(str(e["provider"].currentData() or "") != "manual" for e in self.rows):
            msg = "✓ 本机可用套餐已在下方列表中，点「立即刷新验证」可更新最新数值"
            self._set_status_text(msg)
            ctx.show_toast("本机套餐均已在列表中", "info")
        else:
            self._set_status_text(
                "未扫描到本机自动登录凭据（可点击「+ 添加算力套餐」选择渠道填写 API Key）",
                err=True,
            )
            ctx.show_toast("未发现新的本机凭据", "warn")

    def on_sync_test(self) -> None:
        if self._sync_ctrl.is_busy:
            return
        row_tasks = []
        for idx, e in enumerate(self.rows):
            prov = str(e["provider"].currentData() or "manual")
            if prov == "manual":
                continue
            row_tasks.append((idx, {
                "provider": prov,
                "name": e["name"].text().strip() or prov,
                "apiKey": e["apiKey"].text().strip(),
            }))
        if not row_tasks:
            self._set_status_text(
                "下方列表中暂无自动同步渠道（可点「扫描导入本机套餐」或添加非手动行）",
                err=True,
            )
            return
        if self._test_btn is not None:
            self._test_btn.setEnabled(False)
        self._set_status_text("正在同步各套餐实时用量...")
        self._sync_ctrl.start_sync(row_tasks)

    def on_sync_rows_updated(self, updates: Any) -> None:
        if not isinstance(updates, list):
            return
        for idx, res in updates:
            if not (0 <= idx < len(self.rows)) or not isinstance(res, dict):
                continue
            entry = self.rows[idx]
            if res.get("used") is not None and res.get("limit") is not None:
                set_edit_text(entry["value"], fmt_quota_num(res["used"]))
                set_edit_text(entry["limit"], fmt_quota_num(res["limit"]))
                if res.get("unit") is not None:
                    set_edit_text(entry["unit"], str(res["unit"]))
            elif res.get("balance"):
                set_edit_text(entry["value"], str(res["balance"]))
                set_edit_text(entry["limit"], "")
        if self._ctx is not None:
            self._ctx.schedule_preview()

    def on_sync_finished(self, txt: str) -> None:
        if self._test_btn is not None:
            self._test_btn.setEnabled(True)
        is_err = txt.startswith("✗")
        self._set_status_text(txt, err=is_err)
        if self._ctx is not None:
            self._ctx.show_toast(
                "同步完成" if not is_err else "部分渠道同步失败",
                "danger" if is_err else "ok",
            )

    def load(self, cfg: dict[str, Any]) -> None:
        if self._container is None or self._quota_enable is None:
            return
        self._container.clear_cards()
        self.rows = []
        for q in cfg.get("quotas", []) or []:
            if not isinstance(q, dict):
                continue
            entry = self.add_row()
            p_idx = entry["provider"].findData(str(q.get("provider", "manual") or "manual"))
            entry["provider"].setCurrentIndex(p_idx if p_idx >= 0 else 0)
            entry["baseUrl"] = str(q.get("baseUrl") or "")
            set_edit_text(entry["name"], str(q.get("name", "")))
            set_edit_text(entry["apiKey"], str(q.get("apiKey", "")))
            if "color" in q:
                entry["color"] = str(q.get("color", ""))
            if isinstance(q.get("used"), (int, float)) and isinstance(q.get("limit"), (int, float)):
                set_edit_text(entry["value"], fmt_quota_num(q.get("used")))
                set_edit_text(entry["limit"], fmt_quota_num(q.get("limit")))
            else:
                set_edit_text(entry["value"], str(q.get("balance", q.get("value", ""))))
                set_edit_text(entry["limit"], "")
            set_edit_text(entry["unit"], str(q.get("unit", "")))
            self._sync_row_mode(entry)

        qa = cfg.get("quotaApi") or {}
        self._prev_quota_api = dict(qa)
        self._quota_enable.setChecked(bool(qa.get("enabled", True)))
        self._quota_interval.setValue(int(qa.get("intervalMin", 10)))
        if not self.rows:
            self._populate_initial_rows(qa)

    def collect(self, cfg: dict[str, Any]) -> None:
        if self._quota_enable is None:
            return
        quotas = []
        mp_list = []
        for e in self.rows:
            name = e["name"].text().strip()
            if not name:
                continue
            prov = str(e["provider"].currentData() or "manual")
            row_key = e["apiKey"].text().strip()
            if prov == "magpie" and row_key and row_key not in mp_list:
                mp_list.append(row_key)
            value = e["value"].text().strip()
            limit = e["limit"].text().strip()
            unit = e["unit"].text().strip()
            base_url = str(e.get("baseUrl") or "").strip()
            row_dict: dict[str, Any] = {
                "name": name,
                "provider": prov,
                "apiKey": row_key,
                "color": e.get("color", ""),
            }
            if base_url:
                row_dict["baseUrl"] = base_url
            try:
                used_v = float(value)
                limit_v = float(limit)
                row_dict.update({"used": used_v, "limit": limit_v, "unit": unit})
                quotas.append(row_dict)
                continue
            except (ValueError, TypeError):
                pass
            row_dict.update({"balance": value, "unit": unit, "status": "ok"})
            quotas.append(row_dict)
        cfg["quotas"] = quotas

        prev_qa = cfg.get("quotaApi") or self._prev_quota_api or {}
        cfg["quotaApi"] = {
            "enabled": self._quota_enable.isChecked(),
            "showOnBar": True,
            "source": "magpie" if mp_list else str(prev_qa.get("source", "magpie")),
            "magpieUrl": "http://127.0.0.1:3425",
            "magpieProviders": mp_list,
            "base": str(prev_qa.get("base", "bigmodel")),
            "scope": str(prev_qa.get("scope", "team")),
            "orgId": str(prev_qa.get("orgId", "")),
            "projectId": str(prev_qa.get("projectId", "")),
            "apiKey": str(prev_qa.get("apiKey", "")),
            "intervalMin": self._quota_interval.value(),
        }

    def connect_preview(self) -> None:
        if self._ctx is None or self._quota_enable is None:
            return
        self._quota_enable.stateChanged.connect(self._ctx.schedule_preview)

    def on_scale_changed(self, dark: bool, scale: float) -> None:
        if self._container is not None and self._ctx is not None:
            self._container.set_dark_scale(dark, scale, self._ctx.metrics.row_h, self._ctx.px(6))
