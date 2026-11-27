"""app/gui/hover_panel/cards/dev_card.py — 开发者 Git 工作区状态卡片（支持原位更新与快捷终端）"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from app.core.sources.dev_source import open_repo_terminal
from app.styles import tokens

from ..primitives import (
    Badge,
    TierCard,
    apply_label_color,
    make_card_header,
    make_ghost_link,
    make_label,
    make_transparent_widget,
)
from .base import BasePanelCard, PanelCardContext


class DevPanelCard(BasePanelCard):
    """Git 仓库状态卡片控制器：高内聚管理分支、脏文件计数、终端启动与每 5s 原位刷新。"""

    card_id = "dev"
    source_ids = ("dev",)

    def __init__(self) -> None:
        self.card: QWidget | None = None
        self.widgets: dict = {}

    def reset(self) -> None:
        self.card = None
        self.widgets = {}

    def build(self, ctx: PanelCardContext) -> QWidget | None:
        src_cfg = ctx.cfg.get("sources") or {}
        if not src_cfg.get("dev", {}).get("enabled", True):
            return None
        dev_tiles = ctx.source_tiles.get("dev")
        if not dev_tiles:
            return None

        dark, scale = ctx.dark, ctx.scale
        t = tokens.get_tokens(dark)
        sp = lambda v, lo=1: tokens.spx(v, scale, lo=lo)
        tile = dev_tiles[0]
        branch = str(tile.get("branch") or tile.get("center_text") or "").strip()
        repo_path = str(tile.get("repo_path") or "").strip()
        dirty_count = int(tile.get("dirty_count", 0))
        if not repo_path and not branch:
            return None

        card = TierCard(dark, scale)
        v = QVBoxLayout(card)
        v.setContentsMargins(sp(14, 10), sp(10, 7), sp(14, 10), sp(10, 7))
        v.setSpacing(sp(7, 4))

        term_btn = make_ghost_link("打开终端 ↗", scale, weight=600, hover_tone="accent", px=10.5)
        term_btn.clicked.connect(lambda: open_repo_terminal(self.widgets.get("repo_path", repo_path)))

        dot_color = t.ok_solid if dirty_count == 0 else (t.warn_solid if dirty_count < 10 else t.danger_solid)
        v.addWidget(make_card_header("git", dot_color, "Git 状态", term_btn, dark, scale))

        content_w = make_transparent_widget()
        ch = QHBoxLayout(content_w)
        ch.setContentsMargins(sp(2, 2), 0, sp(2, 2), 0)
        ch.setSpacing(sp(8, 6))

        branch_badge = Badge(branch, t.ok, t.ok_soft, scale, radius=tokens.RADIUS["badge"], weight=700, tone="ok")
        ch.addWidget(branch_badge, 0, Qt.AlignmentFlag.AlignVCenter)

        if dirty_count == 0:
            status_txt, status_color, status_role = "工作区整洁", t.text_muted, "muted"
        else:
            status_txt, status_color, status_role = f"{dirty_count} 个未提交修改", t.warn, "warn"
        status_lbl = make_label(status_txt, 11 * scale, status_color, 600, role=status_role)
        status_lbl.setProperty("_lastColor", status_color)
        ch.addWidget(status_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        ch.addStretch(1)

        repo_name = Path(repo_path).name if repo_path else ""
        repo_lbl = make_label(repo_name, 10.5 * scale, t.text_muted, 500, mono=True, role="muted")
        repo_lbl.setVisible(bool(repo_name))
        ch.addWidget(repo_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        v.addWidget(content_w)

        self.card = card
        self.widgets = {
            "branch": branch_badge,
            "status": status_lbl,
            "repo": repo_lbl,
            "repo_path": repo_path,
        }
        return card

    def try_update_inplace(self, source_id: str, ctx: PanelCardContext) -> bool:
        if source_id != "dev" or self.card is None or self.card.parent() is None or not self.widgets:
            return False
        dev_tiles = ctx.source_tiles.get("dev")
        if not dev_tiles:
            return False
        tile = dev_tiles[0]
        branch = str(tile.get("branch") or tile.get("center_text") or "").strip()
        repo_path = str(tile.get("repo_path") or "").strip()
        dirty_count = int(tile.get("dirty_count", 0))
        if not repo_path and not branch:
            return False

        t = tokens.get_tokens(ctx.dark)
        branch_badge = self.widgets.get("branch")
        status_lbl = self.widgets.get("status")
        repo_lbl = self.widgets.get("repo")
        if branch_badge is not None and branch_badge.text() != branch:
            branch_badge.setText(branch)
        if status_lbl is not None:
            if dirty_count == 0:
                status_txt, status_color, status_role = "工作区整洁", t.text_muted, "muted"
            else:
                status_txt, status_color, status_role = f"{dirty_count} 个未提交修改", t.warn, "warn"
            if status_lbl.text() != status_txt:
                status_lbl.setText(status_txt)
            if status_lbl.property("_lastColor") != status_color:
                status_lbl.setProperty("_lastColor", status_color)
                apply_label_color(status_lbl, status_color, role=status_role)
        if repo_lbl is not None:
            repo_name = Path(repo_path).name if repo_path else ""
            if repo_lbl.text() != repo_name:
                repo_lbl.setText(repo_name)
                repo_lbl.setVisible(bool(repo_name))
        self.widgets["repo_path"] = repo_path
        return True
