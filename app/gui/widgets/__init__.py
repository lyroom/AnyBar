"""app.gui.widgets — 跨窗口共享原子控件与物理动效组件库。"""

from __future__ import annotations

from PySide6.QtGui import QIcon

from app.styles import icons, tokens

from . import motion, scroll_label
from .controls import (
    AnimatedIconButton,
    EditButton,
    SegmentedControl,
    SlidingSegmentedControl,
    ToggleSwitch,
    TrashButton,
)
from .indicators import (
    AnimatedCircularGauge,
    AnimatedProgressBar,
    PulseStatusDot,
    quota_level,
)
from .reorder import AnimatedReorderContainer, ReorderHandle
from .surfaces import SettingGroupCard, SurfaceCard


def build_menu_icons(dark: bool, size: int = 16) -> dict[str, QIcon]:
    return icons.build_menu_icons(dark, size=size)


def app_window_icon() -> QIcon:
    return icons.app_window_icon()


def make_trash_icon(dark: bool) -> QIcon:
    return icons.make_qicon("trash", tokens.get_tokens(dark).text_muted)


__all__ = [
    "AnimatedCircularGauge",
    "AnimatedIconButton",
    "AnimatedProgressBar",
    "AnimatedReorderContainer",
    "EditButton",
    "PulseStatusDot",
    "ReorderHandle",
    "SegmentedControl",
    "SettingGroupCard",
    "SlidingSegmentedControl",
    "SurfaceCard",
    "ToggleSwitch",
    "TrashButton",
    "app_window_icon",
    "build_menu_icons",
    "make_trash_icon",
    "motion",
    "quota_level",
    "scroll_label",
]
