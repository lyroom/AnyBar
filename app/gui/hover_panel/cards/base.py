"""app/gui/hover_panel/cards/base.py — 悬浮窗卡片统一协议（Composite Card 模式）"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from app.gui.hover_panel.panel import HoverPanel


@dataclass
class PanelCardContext:
    """传递给每张卡片构建与刷新时的只读上下文快照。"""

    panel: HoverPanel
    cfg: dict[str, Any]
    dark: bool
    scale: float
    source_tiles: dict[str, list[dict[str, Any]]]
    quota_state: dict[str, Any] | None


class BasePanelCard(ABC):
    """悬浮窗小卡片抽象基类。

    每张卡片独立封装自身 UI 构建、局部子控件引用、原地数值刷新、入场动效与停机清理，
    由 PanelCardRegistry 严格按 cfg['panelCards'] 顺序与开关驱动。
    """

    card_id: str = ""
    aliases: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()

    @abstractmethod
    def build(self, ctx: PanelCardContext) -> QWidget | None:
        """根据当前上下文构建卡片 QWidget；无数据或源未启用时返回 None。"""

    def try_update_inplace(self, source_id: str, ctx: PanelCardContext) -> bool:
        """尝试原地刷新当前卡片数值（避免重建整窗闪烁）；无法原地更新时返回 False。"""
        return False

    def refresh_now(self, ctx: PanelCardContext) -> None:
        """低频定时器触发时的刷新钩子（如日程进度条推进）。"""

    def play_entrance(self) -> None:
        """浮窗首次弹出时触发本卡片内的错峰入场动画。"""

    def stop_animations(self) -> None:
        """浮窗隐藏或关闭时立即停止本卡片全部入场延迟定时器与补间。"""

    def reset(self) -> None:
        """整窗重渲染前重置卡片持有的旧 QWidget 引用。"""
