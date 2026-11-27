"""app.gui.taskbar — 任务栏常驻窗口与自绘条包（Strategy + Registry + Builder）。"""

from .menu_builder import BarContextMenuBuilder, compute_menu_popup_pos
from .views import (
    BarViewRegistry,
    BarViewStrategy,
    VIEW_LABELS,
    VIEW_QUOTA,
    VIEW_SCHEDULE,
    VIEW_SYSTEM,
    VIEW_WEATHER,
)
from .widget import BarWidget
from .window import TaskbarWindow

__all__ = [
    "BarContextMenuBuilder",
    "BarViewRegistry",
    "BarViewStrategy",
    "BarWidget",
    "TaskbarWindow",
    "VIEW_LABELS",
    "VIEW_QUOTA",
    "VIEW_SCHEDULE",
    "VIEW_SYSTEM",
    "VIEW_WEATHER",
    "compute_menu_popup_pos",
]
