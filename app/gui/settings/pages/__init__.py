"""app/gui/settings/pages/__init__.py — 设置中心 6 大标签页导出"""

from .appearance_page import AppearancePage
from .bar_style_page import BarStylePage
from .base import BaseSettingsPage
from .extensions_page import ExtensionsPage
from .plugins_page import PluginsPage
from .schedule_page import SchedulePage
from .todo_page import TodoPage

__all__ = [
    "BaseSettingsPage",
    "SchedulePage",
    "TodoPage",
    "BarStylePage",
    "AppearancePage",
    "ExtensionsPage",
    "PluginsPage",
]
