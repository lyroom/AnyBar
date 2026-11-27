"""app/gui/settings/__init__.py — 设置中心与算力配置向导导出入口"""

from .coding_plan_dialog import CODING_PLAN_PROVIDERS, CodingPlanDialog
from .dialog import SettingsDialog, _normalize_time_str
from .form_helpers import SettingsFormContext, SettingsMetrics, normalize_time_str
from .pages import (
    AppearancePage,
    BarStylePage,
    BaseSettingsPage,
    ExtensionsPage,
    PluginsPage,
    SchedulePage,
    TodoPage,
)
from .quota_controller import QuotaSyncController, discover_local_quota_candidates

__all__ = [
    "SettingsDialog",
    "CodingPlanDialog",
    "CODING_PLAN_PROVIDERS",
    "BaseSettingsPage",
    "SchedulePage",
    "TodoPage",
    "BarStylePage",
    "AppearancePage",
    "ExtensionsPage",
    "PluginsPage",
    "SettingsFormContext",
    "SettingsMetrics",
    "QuotaSyncController",
    "discover_local_quota_candidates",
    "normalize_time_str",
    "_normalize_time_str",
]
