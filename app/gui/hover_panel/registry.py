"""app/gui/hover_panel/registry.py — 悬浮窗卡片注册表（Registry + Composite 生命周期管理）

严格遵循悬浮窗卡片生命周期规范：
所有卡片 100% 遵循用户配置 cfg['panelCards'] 的顺序与 enabled 开关，
严禁绕过 panelCards 强行兜底追加渲染。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QVBoxLayout

from app.core import config as config_mod

from .cards import (
    BasePanelCard,
    DevPanelCard,
    MusicPanelCard,
    PanelCardContext,
    QuotaPanelCard,
    SchedulePanelCard,
    SystemPanelCard,
    TodoPanelCard,
    WeatherPanelCard,
)


class PanelCardRegistry:
    """悬浮窗卡片注册表与生命周期编排器。"""

    def __init__(self) -> None:
        self._cards: dict[str, BasePanelCard] = {}
        self._aliases: dict[str, str] = {}
        self._active_ids: list[str] = []

    def register(self, card: BasePanelCard) -> None:
        self._cards[card.card_id] = card
        for alias in card.aliases:
            self._aliases[alias] = card.card_id

    def resolve_id(self, raw_id: str) -> str:
        cid = str(raw_id or "").strip()
        return self._aliases.get(cid, cid)

    def get(self, card_id: str) -> BasePanelCard | None:
        return self._cards.get(self.resolve_id(card_id))

    def reset_all(self) -> None:
        self._active_ids = []
        for card in self._cards.values():
            card.reset()

    def render_into(self, ctx: PanelCardContext, layout: QVBoxLayout) -> int:
        """严格按照 cfg['panelCards'] 的排序与勾选状态渲染卡片，返回实际渲染张数。"""
        self.reset_all()
        panel_cards = ctx.cfg.get("panelCards")
        if not isinstance(panel_cards, list) or not panel_cards:
            panel_cards = config_mod.DEFAULT_PANEL_CARDS

        rendered_keys: set[str] = set()
        rendered_count = 0
        for item in panel_cards:
            if not isinstance(item, dict):
                continue
            cid = self.resolve_id(str(item.get("id", "")))
            if not cid or cid in rendered_keys:
                continue
            if not item.get("enabled", True):
                continue
            card = self._cards.get(cid)
            if card is None:
                continue
            widget = card.build(ctx)
            if widget is not None:
                layout.addWidget(widget)
                rendered_keys.add(cid)
                self._active_ids.append(cid)
                rendered_count += 1
        return rendered_count

    def is_source_card_shown(self, source_id: str, cfg: dict[str, Any]) -> bool:
        """检查指定数据源对应的面板卡片在当前配置中是否启用且应显示。"""
        if source_id not in ("system", "weather", "dev"):
            return False
        src_cfg = cfg.get("sources") or {}
        if not src_cfg.get(source_id, {}).get("enabled", True):
            return False
        cards = cfg.get("panelCards")
        if not isinstance(cards, list) or not cards:
            return True
        for item in cards:
            if isinstance(item, dict) and self.resolve_id(str(item.get("id", ""))) == source_id:
                return bool(item.get("enabled", True))
        return False

    def dispatch_inplace_update(self, source_id: str, ctx: PanelCardContext) -> bool:
        """将数据源增量更新路由给对应卡片执行原位刷新。"""
        for card in self._cards.values():
            if source_id in card.source_ids:
                return card.try_update_inplace(source_id, ctx)
        return False

    def refresh_all(self, ctx: PanelCardContext) -> None:
        for cid in self._active_ids:
            card = self._cards.get(cid)
            if card is not None:
                card.refresh_now(ctx)

    def play_all_entrances(self) -> None:
        for cid in self._active_ids:
            card = self._cards.get(cid)
            if card is not None:
                card.play_entrance()

    def stop_all_animations(self) -> None:
        for card in self._cards.values():
            card.stop_animations()


def build_default_card_registry() -> PanelCardRegistry:
    """装配全部 7 张官方悬浮窗卡片到注册表。"""
    reg = PanelCardRegistry()
    reg.register(SchedulePanelCard())
    reg.register(TodoPanelCard())
    reg.register(SystemPanelCard())
    reg.register(WeatherPanelCard())
    reg.register(QuotaPanelCard())
    reg.register(DevPanelCard())
    reg.register(MusicPanelCard())
    return reg
