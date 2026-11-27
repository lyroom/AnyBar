"""tests/test_todo_easing.py — 待办打勾微动效属性与交互逻辑测试。"""

import pytest
from app.gui.hover_panel import AppleCheckCircle, TodoRow


def test_apple_check_circle_scale_property(qapp):
    circle = AppleCheckCircle(scale=1.0)
    assert circle.checkScale == 1.0

    circle.checkScale = 0.5
    assert circle.checkScale == 0.5


def test_todo_row_strike_progress_property(qapp):
    todo = {"title": "完成代码评审", "done": False}
    row = TodoRow(0, todo, dark=True, scale=1.0)
    assert row.strikeProgress == 0.0

    row.set_todo({"title": "完成代码评审", "done": True})
    assert row.strikeProgress == 1.0
