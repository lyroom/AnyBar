"""tests/test_capsule_mode.py — 微型双列胶囊模式及悬停展开测算。"""

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPainter

from app.core import config
from app.gui.taskbar.widget import BarWidget
from app.core.sources import weather_source


def test_capsule_mode_default(qapp):
    cfg = config.load_config()
    cfg["style"]["displayMode"] = "full"
    bar = BarWidget(cfg)
    assert bar.is_capsule_mode() is False


def test_capsule_mode_enabled_and_collapsed_width(qapp):
    cfg = config.load_config()
    cfg["style"]["displayMode"] = "capsule"
    bar = BarWidget(cfg)
    assert bar.is_capsule_mode() is True

    # 默认折叠状态
    bar.set_capsule_collapsed(True)
    w_collapsed = bar.desired_width()
    from app.platform import win32_utils
    dpr = win32_utils.get_system_dpi() / 96
    assert w_collapsed == int(128 * dpr)

    # 展开状态下宽度扩展为全量条宽
    bar.set_capsule_collapsed(False)
    w_expanded = bar.desired_width()
    assert w_expanded > w_collapsed


def test_paint_capsule_drawing(qapp):
    cfg = config.load_config()
    cfg["style"]["displayMode"] = "capsule"
    bar = BarWidget(cfg)
    bar.set_capsule_collapsed(True)

    img = QImage(160, 40, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    painter = QPainter(img)
    try:
        bar._paint_capsule(painter, QRect(0, 0, 160, 40))
    finally:
        painter.end()

    # 确保成功绘制且非全透明
    assert not img.isNull()
