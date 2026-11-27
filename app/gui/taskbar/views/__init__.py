"""app/gui/taskbar/views/__init__.py — 常驻条视图策略基类与注册表（Strategy + Registry 模式）"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter

if TYPE_CHECKING:
    from app.gui.taskbar.widget import BarWidget

VIEW_SCHEDULE = "schedule"
VIEW_SYSTEM = "system"
VIEW_QUOTA = "quota"
VIEW_WEATHER = "weather"

VIEW_LABELS: dict[str, str] = {
    VIEW_SCHEDULE: "日程待办",
    VIEW_SYSTEM: "系统硬件",
    VIEW_QUOTA: "算力套餐",
    VIEW_WEATHER: "实时天气",
}


class BarViewStrategy(ABC):
    """任务栏常驻条视图渲染策略抽象基类。"""

    view_id: str = ""
    label: str = ""

    @abstractmethod
    def is_available(self, bar: BarWidget) -> bool:
        """当前配置与数据状态下，该视图是否可用。"""

    @abstractmethod
    def desired_width(self, bar: BarWidget, h: float, dpr: float) -> int:
        """测算当前视图所需的物理像素宽度。"""

    @abstractmethod
    def paint(self, bar: BarWidget, painter: QPainter, r: QRect) -> None:
        """在液态玻璃底板之上绘制本视图内容。"""


class BarViewRegistry:
    """常驻条视图策略注册表：统一管理可用视图顺序与策略路由。"""

    def __init__(self) -> None:
        self._strategies: dict[str, BarViewStrategy] = {}

    def register(self, strategy: BarViewStrategy) -> None:
        self._strategies[strategy.view_id] = strategy

    def get(self, view_id: str) -> BarViewStrategy | None:
        return self._strategies.get(view_id)

    def available_views(self, bar: BarWidget) -> list[str]:
        return [vid for vid, strat in self._strategies.items() if strat.is_available(bar)]

    def ordered_ids(self) -> list[str]:
        return list(self._strategies.keys())


def build_default_view_registry() -> BarViewRegistry:
    """按固定视觉轮转顺序装配默认视图策略注册表。"""
    from .schedule_view import ScheduleViewStrategy
    from .tiles_view import TilesViewStrategy
    from .weather_view import WeatherViewStrategy

    reg = BarViewRegistry()
    reg.register(ScheduleViewStrategy())
    reg.register(TilesViewStrategy(view_id=VIEW_SYSTEM, label=VIEW_LABELS[VIEW_SYSTEM], is_system=True))
    reg.register(WeatherViewStrategy())
    reg.register(TilesViewStrategy(view_id=VIEW_QUOTA, label=VIEW_LABELS[VIEW_QUOTA], is_system=False))
    return reg


__all__ = [
    "BarViewRegistry",
    "BarViewStrategy",
    "VIEW_LABELS",
    "VIEW_QUOTA",
    "VIEW_SCHEDULE",
    "VIEW_SYSTEM",
    "VIEW_WEATHER",
    "build_default_view_registry",
]
