"""app/gui/settings/coding_plan_dialog.py — 算力套餐配置向导弹窗（样式全由 dialogs.qss + common.qss 驱动）"""

from __future__ import annotations

import os
import threading
from typing import Any

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app.core import quota_api
from app.core.quota_api import QuotaError, fetch_provider_quota  # noqa: F401
from app.gui import widgets as ui_parts
from app.gui.widgets import motion
from app.platform import glass
from app.styles import icons, qss_engine, theme, tokens

CODING_PLAN_PROVIDERS = [
    ("glm", "智谱 GLM Coding Plan (直连)", "官方直连，支持个人与团队套餐，多窗口限额监控"),
    ("codex", "ChatGPT Codex (OAuth / 直连)", "自动读取本机 ~/.codex 或填入 Token，监控 5h/7d 窗口"),
    ("claude", "Claude / Anthropic (直连)", "Anthropic 官方直连，监控 Token 消耗与 RPM/TPM 限速"),
    ("cursor", "Cursor Fast Requests (直连)", "Cursor Pro / Business 快速请求配额与月度重置倒计时"),
    ("deepseek", "DeepSeek 开放平台 (直连)", "DeepSeek 账户实时可用余额与代金券健康度监控"),
    ("openai", "OpenAI 官方 API (直连)", "OpenAI 开发者账户月度硬性限额 (Hard Cap) 与速率限制"),
    ("kimi", "Moonshot Kimi (直连)", "Moonshot 开放平台实时可用余额监控"),
    ("openrouter", "OpenRouter 额度 (直连)", "OpenRouter 多模型中转平台账户总积分与用量"),
    ("newapi", "NewAPI / OneAPI 中转", "兼容 NewAPI、OneAPI 等 OpenAI 格式聚合分发网关"),
    ("magpie", "Magpie 本地网关 (聚合同步)", "从本机运行的 Magpie 网关自动获取全部已登录工具额度"),
    ("manual", "手动填写 (自定义展示)", "离线自定义当前数值、上限与单位"),
]


class _AsyncTestWorker(QObject):
    """异步测试连通性工作对象。"""

    finished = Signal(bool, str, dict)

    def __init__(self, item: dict[str, Any], parent=None):
        super().__init__(parent)
        self._item = item

    def run(self):
        try:
            res = fetch_provider_quota(self._item, timeout=8.0)
            prov = str(self._item.get("provider") or "").lower()
            name = str(self._item.get("name") or prov).capitalize()
            parts = [f"✓ {name} 连接成功"]

            plan = res.get("plan") or res.get("level")
            if plan:
                parts.append(f"套餐：{plan}")

            wins = res.get("windows") or []
            prim_w = quota_api.primary_window(wins)
            if prim_w:
                w_name = prim_w.get("name") or "窗口"
                rem_pct = prim_w.get("remaining_percent")
                if rem_pct is None and prim_w.get("percent") is not None:
                    rem_pct = round(100.0 - float(prim_w["percent"]), 1)
                if rem_pct is not None:
                    parts.append(f"{w_name}剩余 {int(round(rem_pct))}%")
                if prim_w.get("display"):
                    parts.append(f"({prim_w['display']})")
            elif res.get("balance"):
                parts.append(f"可用余额：{res['balance']}")
            elif res.get("used") is not None and res.get("limit") is not None:
                parts.append(f"用量：{res['used']} / {res['limit']} {res.get('unit', '')}")

            self.finished.emit(True, " · ".join(parts), res)
        except Exception as e:
            self.finished.emit(False, f"✗ 连接失败：{e}", {})


class CodingPlanDialog(QDialog):
    """配置具体 Coding Plan 的专属向导弹窗（全套样式由外部 dialogs.qss 编译挂载）。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        item_data: dict[str, Any] | None = None,
        dark: bool = True,
        scale: float = 1.0,
    ):
        super().__init__(parent)
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self._item_data = dict(item_data or {})
        self._is_edit = bool(item_data)
        self._test_result_data: dict[str, Any] = {}

        self.setWindowTitle("编辑算力套餐 · Coding Plan" if self._is_edit else "添加算力套餐 · Coding Plan")
        self.setWindowIcon(ui_parts.app_window_icon())
        self.setMinimumWidth(self._px(560))
        self.setModal(True)
        self.setFont(theme.ui_font(12.5 * self._scale, 400))
        self.setStyleSheet(theme.dialog_qss(self._dark, self._scale))

        self._build_ui()
        self._load_item_data()

    def showEvent(self, event):
        super().showEvent(event)
        try:
            hwnd = int(self.winId())
            if hwnd:
                glass.style_titlebar(hwnd, self._dark)
        except Exception:
            pass

    def _px(self, v: float) -> int:
        return tokens.spx(v, self._scale)

    def _style_combo(self, combo: QComboBox) -> None:
        t = tokens.get_tokens(self._dark)
        view = combo.view()
        view.setAutoFillBackground(True)
        pal = view.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(t.menu_bg))
        pal.setColor(QPalette.ColorRole.Text, QColor(t.text))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(t.surface_hover))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(t.text))
        view.setPalette(pal)

    def _make_btn(self, text: str, icon_name: str = "", primary: bool = False) -> QPushButton:
        t = tokens.get_tokens(self._dark)
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoDefault(False)
        btn.setDefault(False)
        if primary:
            btn.setObjectName("primaryBtn")
        if icon_name:
            ic_sz = self._px(14)
            btn.setIcon(icons.make_qicon(icon_name, t.text_on_accent if primary else t.icon, size=ic_sz))
            btn.setIconSize(QSize(ic_sz, ic_sz))
        return btn

    def _make_muted_hint(self, text: str = "", left_margin: int = 88) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setFont(theme.ui_font(11 * self._scale, 400))
        qss_engine.set_role(lbl, "muted", polish=False)
        if left_margin > 0:
            lbl.setContentsMargins(self._px(left_margin), 0, 0, 0)
        return lbl

    def _make_divider(self) -> QFrame:
        div = QFrame()
        div.setFixedHeight(1)
        qss_engine.set_role(div, "divider", polish=False)
        return div

    def _build_ui(self) -> None:
        t = tokens.get_tokens(self._dark)
        root = QVBoxLayout(self)
        root.setContentsMargins(self._px(20), self._px(16), self._px(20), self._px(16))
        root.setSpacing(self._px(12))

        tip_card = QFrame()
        tip_card.setObjectName("wizardTipCard")
        th = QHBoxLayout(tip_card)
        th.setContentsMargins(self._px(12), self._px(9), self._px(12), self._px(9))
        th.setSpacing(self._px(9))
        th.addWidget(icons.IconWidget("info", t.accent, size=self._px(16)), 0, Qt.AlignmentFlag.AlignTop)
        tip_text = QLabel("可直连官方 API，或留空自动读取本机 CLI 凭证；点击下方「测试连接」验证成功后即可一键加入任务栏。")
        tip_text.setWordWrap(True)
        tip_text.setFont(theme.ui_font(12 * self._scale, 500))
        qss_engine.set_role(tip_text, "primary", polish=False)
        th.addWidget(tip_text, 1)
        root.addWidget(tip_card)

        form_card = ui_parts.SurfaceCard(self._dark, self._scale, radius=tokens.RADIUS["card"])
        fv = QVBoxLayout(form_card)
        fv.setContentsMargins(self._px(16), self._px(14), self._px(16), self._px(14))
        fv.setSpacing(self._px(10))

        row_prov = QHBoxLayout()
        row_prov.setSpacing(self._px(10))
        lbl_prov = QLabel("平台类型")
        lbl_prov.setFixedWidth(self._px(78))
        row_prov.addWidget(lbl_prov)

        self._prov_combo = QComboBox()
        for pid, label, _desc in CODING_PLAN_PROVIDERS:
            self._prov_combo.addItem(label, pid)
        self._prov_combo.setFixedHeight(self._px(34))
        self._style_combo(self._prov_combo)
        self._prov_combo.currentIndexChanged.connect(self._on_provider_changed)
        row_prov.addWidget(self._prov_combo, 1)
        fv.addLayout(row_prov)

        self._prov_desc_lbl = self._make_muted_hint("")
        fv.addWidget(self._prov_desc_lbl)

        row_name = QHBoxLayout()
        row_name.setSpacing(self._px(10))
        lbl_name = QLabel("显示名称")
        lbl_name.setFixedWidth(self._px(78))
        row_name.addWidget(lbl_name)

        self._name_edit = QLineEdit()
        self._name_edit.setFixedHeight(self._px(34))
        self._name_edit.setPlaceholderText("在任务栏与悬浮窗展示的名称")
        row_name.addWidget(self._name_edit, 1)
        fv.addLayout(row_name)

        fv.addWidget(self._make_divider())

        self._param_stack = motion.AnimatedStackedWidget(duration=tokens.MOTION["fast"])
        self._page_api_key = self._build_api_key_page()
        self._page_glm = self._build_glm_page()
        self._page_magpie = self._build_magpie_page()
        self._page_manual = self._build_manual_page()

        self._param_stack.addWidget(self._page_api_key)
        self._param_stack.addWidget(self._page_glm)
        self._param_stack.addWidget(self._page_magpie)
        self._param_stack.addWidget(self._page_manual)
        fv.addWidget(self._param_stack)
        root.addWidget(form_card)

        test_card = ui_parts.SurfaceCard(self._dark, self._scale, radius=tokens.RADIUS["card"], elevated=True)
        tv = QVBoxLayout(test_card)
        tv.setContentsMargins(self._px(14), self._px(12), self._px(14), self._px(12))
        tv.setSpacing(self._px(8))

        th_act = QHBoxLayout()
        th_act.setSpacing(self._px(10))
        self._test_btn = self._make_btn("测试连接并获取用量", "bolt", primary=True)
        self._test_btn.setFixedHeight(self._px(34))
        self._test_btn.clicked.connect(self._on_test_connection)
        th_act.addWidget(self._test_btn, 0)

        self._test_tip_lbl = self._make_muted_hint("建议保存前测试一次，可自动拉取当前套餐档位与剩余额度", left_margin=0)
        th_act.addWidget(self._test_tip_lbl, 1, Qt.AlignmentFlag.AlignVCenter)
        tv.addLayout(th_act)

        self._test_status_lbl = QLabel("等待测试连接")
        self._test_status_lbl.setObjectName("wizardStatus")
        self._test_status_lbl.setWordWrap(True)
        self._test_status_lbl.setFont(theme.ui_font(12 * self._scale, 500))
        tv.addWidget(self._test_status_lbl)
        root.addWidget(test_card)

        root.addStretch(1)
        root.addWidget(self._make_divider())

        bh = QHBoxLayout()
        bh.setSpacing(self._px(10))
        bh.addStretch(1)

        self._cancel_btn = self._make_btn("取消")
        self._cancel_btn.setFixedSize(self._px(88), self._px(35))
        self._cancel_btn.clicked.connect(self.reject)
        bh.addWidget(self._cancel_btn)

        self._ok_btn = self._make_btn("保存修改" if self._is_edit else "保存并添加", "check", primary=True)
        self._ok_btn.setFixedSize(self._px(116), self._px(35))
        self._ok_btn.clicked.connect(self.accept)
        bh.addWidget(self._ok_btn)
        root.addLayout(bh)

    def _build_api_key_page(self) -> QWidget:
        w = QWidget()
        w.setObjectName("paramPage")
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(self._px(8))

        h = QHBoxLayout()
        h.setSpacing(self._px(10))
        lbl = QLabel("连接凭证")
        lbl.setFixedWidth(self._px(78))
        h.addWidget(lbl)

        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setFixedHeight(self._px(34))
        h.addWidget(self._api_key_edit, 1)

        self._detect_btn = self._make_btn("探测本机", "search")
        self._detect_btn.setFixedHeight(self._px(34))
        self._detect_btn.clicked.connect(self._on_detect_credentials)
        h.addWidget(self._detect_btn)
        v.addLayout(h)

        self._base_url_layout = QHBoxLayout()
        self._base_url_layout.setSpacing(self._px(10))
        lbl_url = QLabel("端点地址")
        lbl_url.setFixedWidth(self._px(78))
        self._base_url_layout.addWidget(lbl_url)

        self._base_url_edit = QLineEdit()
        self._base_url_edit.setFixedHeight(self._px(34))
        self._base_url_edit.setPlaceholderText("https://api.example.com (留空为官方默认)")
        self._base_url_layout.addWidget(self._base_url_edit, 1)
        v.addLayout(self._base_url_layout)

        self._key_hint_lbl = self._make_muted_hint("")
        v.addWidget(self._key_hint_lbl)
        return w

    def _build_glm_page(self) -> QWidget:
        w = QWidget()
        w.setObjectName("paramPage")
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(self._px(8))

        h_scope = QHBoxLayout()
        h_scope.setSpacing(self._px(10))
        lbl_site = QLabel("站点 / 范围")
        lbl_site.setFixedWidth(self._px(78))
        h_scope.addWidget(lbl_site)

        self._glm_site_combo = QComboBox()
        self._glm_site_combo.addItem("国内版 (open.bigmodel.cn)", "bigmodel")
        self._glm_site_combo.addItem("国际版 (api.z.ai)", "zai")
        self._glm_site_combo.setFixedHeight(self._px(34))
        self._style_combo(self._glm_site_combo)
        h_scope.addWidget(self._glm_site_combo, 1)

        self._glm_personal_check = QRadioButton("个人套餐")
        self._glm_team_check = QRadioButton("团队套餐")
        self._glm_personal_check.setChecked(True)
        h_scope.addWidget(self._glm_personal_check)
        h_scope.addWidget(self._glm_team_check)
        v.addLayout(h_scope)

        h_key = QHBoxLayout()
        h_key.setSpacing(self._px(10))
        lbl_k = QLabel("GLM Key")
        lbl_k.setFixedWidth(self._px(78))
        h_key.addWidget(lbl_k)

        self._glm_key_edit = QLineEdit()
        self._glm_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._glm_key_edit.setFixedHeight(self._px(34))
        self._glm_key_edit.setPlaceholderText("填入智谱 Coding Plan API Key")
        h_key.addWidget(self._glm_key_edit, 1)

        self._glm_detect_btn = self._make_btn("探测 ZCode", "search")
        self._glm_detect_btn.setFixedHeight(self._px(34))
        self._glm_detect_btn.clicked.connect(self._on_detect_zcode)
        h_key.addWidget(self._glm_detect_btn)
        v.addLayout(h_key)

        v.addWidget(self._make_muted_hint("团队套餐需携带团队上下文头；点击「探测 ZCode」可自动发现本机组织与项目 ID"))
        return w

    def _build_magpie_page(self) -> QWidget:
        w = QWidget()
        w.setObjectName("paramPage")
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(self._px(8))

        h_gw = QHBoxLayout()
        h_gw.setSpacing(self._px(10))
        lbl_gw = QLabel("网关地址")
        lbl_gw.setFixedWidth(self._px(78))
        h_gw.addWidget(lbl_gw)

        self._magpie_url_edit = QLineEdit("http://127.0.0.1:3425")
        self._magpie_url_edit.setFixedHeight(self._px(34))
        h_gw.addWidget(self._magpie_url_edit, 1)
        v.addLayout(h_gw)

        h_ch = QHBoxLayout()
        h_ch.setSpacing(self._px(10))
        lbl_ch = QLabel("同步渠道")
        lbl_ch.setFixedWidth(self._px(78))
        h_ch.addWidget(lbl_ch)

        self._magpie_ch_combo = QComboBox()
        self._magpie_ch_combo.setFixedHeight(self._px(34))
        self._magpie_ch_combo.setEditable(True)
        self._style_combo(self._magpie_ch_combo)
        h_ch.addWidget(self._magpie_ch_combo, 1)

        self._magpie_scan_btn = self._make_btn("扫描渠道", "refresh")
        self._magpie_scan_btn.setFixedHeight(self._px(34))
        self._magpie_scan_btn.clicked.connect(self._scan_magpie_channels)
        h_ch.addWidget(self._magpie_scan_btn)
        v.addLayout(h_ch)

        v.addWidget(self._make_muted_hint("自动连接本机 Magpie（127.0.0.1:3425）或 ~/.config/magpie/quotas.json 缓存"))
        return w

    def _build_manual_page(self) -> QWidget:
        w = QWidget()
        w.setObjectName("paramPage")
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(self._px(8))

        h = QHBoxLayout()
        h.setSpacing(self._px(10))
        lbl = QLabel("用量 / 上限")
        lbl.setFixedWidth(self._px(78))
        h.addWidget(lbl)

        self._manual_val_edit = QLineEdit()
        self._manual_val_edit.setPlaceholderText("用量或余额 (如 340 或 ¥18.5)")
        self._manual_val_edit.setFixedHeight(self._px(34))
        h.addWidget(self._manual_val_edit, 2)

        h.addWidget(QLabel("/"))

        self._manual_lim_edit = QLineEdit()
        self._manual_lim_edit.setPlaceholderText("上限 (如 500)")
        self._manual_lim_edit.setFixedHeight(self._px(34))
        h.addWidget(self._manual_lim_edit, 2)

        self._manual_unit_edit = QLineEdit()
        self._manual_unit_edit.setPlaceholderText("单位 (req / %)")
        self._manual_unit_edit.setFixedHeight(self._px(34))
        h.addWidget(self._manual_unit_edit, 1)
        v.addLayout(h)
        return w

    def _on_provider_changed(self) -> None:
        prov = str(self._prov_combo.currentData() or "glm").lower()
        spec = next((s for s in CODING_PLAN_PROVIDERS if s[0] == prov), None)
        if spec:
            self._prov_desc_lbl.setText(spec[2])

        default_names = {
            "glm": "GLM", "codex": "Codex", "claude": "Claude",
            "cursor": "Cursor", "deepseek": "DeepSeek", "openai": "OpenAI",
            "kimi": "Kimi", "openrouter": "OpenRouter", "newapi": "NewAPI",
            "magpie": "Magpie", "manual": "自定义套餐",
        }
        if not self._is_edit or not self._name_edit.text().strip():
            self._name_edit.setText(default_names.get(prov, prov.capitalize()))

        if prov == "glm":
            self._param_stack.setCurrentWidget(self._page_glm)
        elif prov == "magpie":
            self._param_stack.setCurrentWidget(self._page_magpie)
            self._scan_magpie_channels()
        elif prov == "manual":
            self._param_stack.setCurrentWidget(self._page_manual)
        else:
            self._param_stack.setCurrentWidget(self._page_api_key)
            is_newapi = prov in ("newapi", "kimi")
            for i in range(self._base_url_layout.count()):
                w = self._base_url_layout.itemAt(i).widget()
                if w:
                    w.setVisible(is_newapi)
            hints = {
                "codex": "留空可自动读取本机 ~/.codex/auth.json OAuth，也可手动粘贴 Token",
                "claude": "填写 Anthropic API Key (sk-ant-...)，或留空读取 ~/.claude.json",
                "cursor": "填写 WorkosCursorSessionToken，或留空自动探测本地 Cursor 存储",
                "deepseek": "填写 DeepSeek API Key (sk-...)，或读取 DEEPSEEK_API_KEY 环境变量",
                "openai": "填写 OpenAI API Key (sk-...)，或读取 OPENAI_API_KEY 环境变量",
                "kimi": "填写 Moonshot Kimi API Key",
                "openrouter": "填写 OpenRouter API Key (sk-or-...)",
                "newapi": "填写 NewAPI 令牌与 API 基础地址",
            }
            self._key_hint_lbl.setText(hints.get(prov, ""))

    def _on_detect_credentials(self) -> None:
        prov = str(self._prov_combo.currentData() or "").lower()
        if prov == "codex":
            auth = quota_api.discover_codex_auth()
            if auth:
                self._api_key_edit.setText(auth.get("access_token", ""))
                self._set_status(f"✓ 已探测到本机 Codex OAuth 凭据 (Plan: {auth.get('plan', 'Plus')})", success=True)
            else:
                self._set_status("未在 ~/.codex/auth.json 中找到 Codex 凭据，请手动粘贴 Token", success=False)
        elif prov == "claude":
            from app.core.sources.claude_source import discover_claude_auth
            auth = discover_claude_auth()
            if auth and auth.get("apiKey"):
                self._api_key_edit.setText(auth["apiKey"])
                self._set_status(f"✓ 已从 {auth.get('source')} 探测到 Claude 凭证", success=True)
            else:
                self._set_status("未检测到本机 Claude 凭据，请手动填入 Anthropic API Key", success=False)
        elif prov == "cursor":
            from app.core.sources.cursor_source import discover_cursor_session
            tok = discover_cursor_session()
            if tok:
                self._api_key_edit.setText(tok)
                self._set_status("✓ 已探测到本机 Cursor Session Token", success=True)
            else:
                self._set_status("未检测到本机 Cursor 会话，请手动粘贴 WorkosCursorSessionToken", success=False)
        elif prov == "deepseek":
            k = os.environ.get("DEEPSEEK_API_KEY", "").strip()
            if k:
                self._api_key_edit.setText(k)
                self._set_status("✓ 已从系统环境变量 DEEPSEEK_API_KEY 载入凭据", success=True)
            else:
                self._set_status("未找到环境变量 DEEPSEEK_API_KEY，请手动填入", success=False)
        elif prov == "openai":
            k = os.environ.get("OPENAI_API_KEY", "").strip()
            if k:
                self._api_key_edit.setText(k)
                self._set_status("✓ 已从系统环境变量 OPENAI_API_KEY 载入凭据", success=True)
            else:
                self._set_status("未找到环境变量 OPENAI_API_KEY，请手动填入", success=False)
        else:
            self._set_status("当前渠道不支持本地自动探测，请手动填写", success=False)

    def _on_detect_zcode(self) -> None:
        site = str(self._glm_site_combo.currentData() or "bigmodel")
        ctx = quota_api.discover_team_context(base=site)
        if ctx and ctx.get("org") and ctx.get("project"):
            self._glm_team_check.setChecked(True)
            self._set_status(f"✓ 已自动发现 ZCode 团队上下文 (Org: {ctx['org'][:8]}...)", success=True)
        else:
            self._set_status("未检测到 ~/.zcode/v2/credentials.json 团队凭据，默认采用个人套餐模式", success=False)

    def _scan_magpie_channels(self) -> None:
        url = self._magpie_url_edit.text().strip() or "http://127.0.0.1:3425"
        try:
            cards = quota_api.fetch_magpie_quotas(url, timeout=2.0)
            self._magpie_ch_combo.clear()
            if cards:
                for c in cards:
                    p = str(c.get("provider") or "").strip()
                    title = str(c.get("title") or c.get("name") or p)
                    self._magpie_ch_combo.addItem(f"{title} ({p})", p)
                self._set_status(f"✓ 已从 Magpie 发现 {len(cards)} 个可用渠道", success=True)
            else:
                for ch in ("zcode", "codex", "codearts"):
                    self._magpie_ch_combo.addItem(ch, ch)
        except Exception as e:
            self._set_status(f"Magpie 扫描提示：{e}", success=False)

    def _collect_current_payload(self) -> dict[str, Any]:
        prov = str(self._prov_combo.currentData() or "manual").lower()
        name = self._name_edit.text().strip() or prov.capitalize()
        item: dict[str, Any] = {"provider": prov, "name": name}

        if prov == "glm":
            item["apiKey"] = self._glm_key_edit.text().strip()
            item["baseUrl"] = str(self._glm_site_combo.currentData() or "bigmodel")
            item["scope"] = "team" if self._glm_team_check.isChecked() else "personal"
            if item["scope"] == "team":
                ctx = quota_api.discover_team_context(base=item["baseUrl"])
                if ctx:
                    item["orgId"] = ctx.get("org", "")
                    item["projectId"] = ctx.get("project", "")
        elif prov == "magpie":
            item["baseUrl"] = self._magpie_url_edit.text().strip() or "http://127.0.0.1:3425"
            ch = self._magpie_ch_combo.currentData() or self._magpie_ch_combo.currentText().strip()
            item["apiKey"] = str(ch).strip()
        elif prov == "manual":
            item["value"] = self._manual_val_edit.text().strip()
            item["limit"] = self._manual_lim_edit.text().strip()
            item["unit"] = self._manual_unit_edit.text().strip()
        else:
            item["apiKey"] = self._api_key_edit.text().strip()
            burl = self._base_url_edit.text().strip()
            if burl:
                item["baseUrl"] = burl

        if self._test_result_data:
            item.update(self._test_result_data)
        elif self._item_data:
            for k in ("used", "limit", "unit", "balance", "plan", "windows", "value", "color"):
                if k in self._item_data and k not in item:
                    item[k] = self._item_data[k]
        return item

    def _on_test_connection(self) -> None:
        payload = self._collect_current_payload()
        prov = payload.get("provider", "manual")
        if prov == "manual":
            self._set_status("✓ 手动填写模式无需网络测试，保存即可展示", success=True)
            return

        self._test_btn.setEnabled(False)
        self._test_btn.setText("正在测试...")
        self._test_status_lbl.setText(f"正在连接 {prov.upper()} 接口...")
        qss_engine.set_prop(self._test_status_lbl, "state", "loading")

        self._test_worker = _AsyncTestWorker(payload, parent=self)
        thread = threading.Thread(target=self._test_worker.run, daemon=True)

        def on_finished(success: bool, msg: str, res_data: dict):
            self._test_btn.setEnabled(True)
            self._test_btn.setText("测试连接并获取用量")
            self._set_status(msg, success=success)
            if success and res_data:
                self._test_result_data = res_data
                if res_data.get("used") is not None and res_data.get("limit") is not None:
                    self._item_data["used"] = res_data["used"]
                    self._item_data["limit"] = res_data["limit"]
                    self._item_data["unit"] = res_data.get("unit", "")
                if res_data.get("balance"):
                    self._item_data["balance"] = res_data["balance"]
                if res_data.get("windows"):
                    self._item_data["windows"] = res_data["windows"]
                if res_data.get("plan"):
                    self._item_data["plan"] = res_data["plan"]
            if self._test_worker is not None:
                self._test_worker.deleteLater()
                self._test_worker = None

        self._test_worker.finished.connect(on_finished)
        thread.start()

    def _set_status(self, msg: str, success: bool) -> None:
        self._test_status_lbl.setText(msg)
        qss_engine.set_prop(self._test_status_lbl, "state", "ok" if success else "danger")

    def _load_item_data(self) -> None:
        if not self._item_data:
            self._prov_combo.setCurrentIndex(0)
            self._on_provider_changed()
            return

        prov = str(self._item_data.get("provider") or "manual").lower()
        idx = self._prov_combo.findData(prov)
        if idx >= 0:
            self._prov_combo.setCurrentIndex(idx)
        self._on_provider_changed()

        if self._item_data.get("name"):
            self._name_edit.setText(str(self._item_data["name"]))

        key = str(self._item_data.get("apiKey") or "")
        burl = str(self._item_data.get("baseUrl") or "")

        if prov == "glm":
            self._glm_key_edit.setText(key)
            if burl in ("bigmodel", "zai"):
                b_idx = self._glm_site_combo.findData(burl)
                if b_idx >= 0:
                    self._glm_site_combo.setCurrentIndex(b_idx)
            if str(self._item_data.get("scope", "")) == "team":
                self._glm_team_check.setChecked(True)
        elif prov == "magpie":
            if burl:
                self._magpie_url_edit.setText(burl)
            if key:
                c_idx = self._magpie_ch_combo.findData(key)
                if c_idx >= 0:
                    self._magpie_ch_combo.setCurrentIndex(c_idx)
                else:
                    self._magpie_ch_combo.setEditText(key)
        elif prov == "manual":
            v = self._item_data.get("value", self._item_data.get("balance", ""))
            lim = self._item_data.get("limit", "")
            u = self._item_data.get("unit", "")
            self._manual_val_edit.setText(str(v) if v is not None else "")
            self._manual_lim_edit.setText(str(lim) if lim is not None else "")
            self._manual_unit_edit.setText(str(u) if u is not None else "")
        else:
            self._api_key_edit.setText(key)
            if burl:
                self._base_url_edit.setText(burl)

    def get_data(self) -> dict[str, Any]:
        payload = self._collect_current_payload()
        if self._test_result_data:
            for k in ("used", "limit", "unit", "balance", "windows", "plan", "level", "status"):
                if self._test_result_data.get(k) is not None:
                    payload[k] = self._test_result_data[k]
        elif self._item_data:
            for k in ("used", "limit", "unit", "balance", "windows", "plan", "level", "status", "color"):
                if self._item_data.get(k) is not None and k not in payload:
                    payload[k] = self._item_data[k]
        return payload
