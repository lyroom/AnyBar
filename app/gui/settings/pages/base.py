"""app/gui/settings/pages/base.py — 设置中心标签页统一协议（Page Presenter 模式）"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from PySide6.QtWidgets import QWidget

from ..form_helpers import SettingsFormContext


class BaseSettingsPage(ABC):
    """设置标签页抽象基类：每个标签页高内聚封装自身的构建、回填、收集与实时预览绑定。"""

    page_id: str = ""
    title: str = ""

    def __init__(self) -> None:
        self._ctx: SettingsFormContext | None = None

    @abstractmethod
    def build(self, ctx: SettingsFormContext) -> QWidget:
        """构建标签页根控件。"""

    @abstractmethod
    def load(self, cfg: dict[str, Any]) -> None:
        """从配置字典回填本页所有控件值。"""

    @abstractmethod
    def collect(self, cfg: dict[str, Any]) -> None:
        """收集本页表单数据写回配置字典。"""

    def connect_preview(self) -> None:
        """将本页所有输入控件变更信号绑定到防抖预览回调。"""

    def apply_side_effects(self) -> None:
        """保存/应用时的可选系统副作用（如开机自启注册表写入）。"""

    def on_scale_changed(self, dark: bool, scale: float) -> None:
        """窗口跨屏 DPI 变化时通知含自定义排序容器的页面同步度量。"""
