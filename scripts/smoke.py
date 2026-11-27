"""scripts/smoke.py — 离屏冒烟测试与内存泄漏验证套件（用于 CI 与发布前验证）。

在无真实物理窗口环境下（QT_QPA_PLATFORM=offscreen），
验证 BarWidget 与 HoverPanel 的 QMenu、QAction、QPropertyAnimation 与 QWidget 子树
在反复弹出、悬停、右键菜单和数据源重渲染下对象计数严格保持恒定，杜绝内存泄漏。
"""

from __future__ import annotations

import copy
import gc
import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
os.environ["TOUCHBAR_NO_SWP"] = "1"  # offscreen 句柄非真窗口，跳过 SWP

# 确保项目根路径进入 sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PySide6.QtCore import QEvent, QPropertyAnimation, QRect, QTimer
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from app.core import config as config_mod
from app.gui.taskbar.widget import BarWidget
from app.gui.hover_panel import HoverPanel


def flush():
    for _ in range(3):
        QTest.qWait(20)
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()


def _close_open_menus():
    for w in QApplication.topLevelWidgets():
        if isinstance(w, QMenu) and w.isVisible():
            w.close()


def run_smoke():
    app = QApplication.instance() or QApplication([])
    cfg = copy.deepcopy(config_mod.DEFAULT_CONFIG)

    print("=== [1/4] BarWidget 右键菜单生命周期测试 ===", flush=True)
    bar = BarWidget(cfg)
    bar._tick_timer.stop()
    bar._minute_timer.stop()

    for _ in range(20):
        QTimer.singleShot(150, _close_open_menus)
        bar._show_menu(None)
    flush()
    menus = bar.findChildren(QMenu)
    actions = bar.findChildren(QAction)
    print(f"20 次右键菜单操作后: QMenu={len(menus)} QAction={len(actions)} (预期 0/0)", flush=True)
    assert not menus and not actions, "QMenu/QAction 对象累积泄漏！"

    print("=== [2/4] HoverPanel 弹出/隐藏周期动画测试 ===", flush=True)
    panel = HoverPanel()
    for i in range(5):
        panel.popup(cfg, QRect(100, 500, 300, 40))
        QTest.qWait(400)
        panel.schedule_hide()
        QTest.qWait(700)
        assert not panel.isVisible(), f"第 {i} 周期未正确隐藏"

    print("=== [3/4] keep_alive 中断隐藏动画打断恢复测试 ===", flush=True)
    panel.popup(cfg, QRect(100, 500, 300, 40))
    QTest.qWait(400)
    panel.schedule_hide()
    QTest.qWait(320)
    panel.keep_alive()
    QTest.qWait(300)
    panel.schedule_hide()
    QTest.qWait(700)

    print("=== [4/4] Tiles/Quota 反复重渲染浸泡测试 ===", flush=True)
    panel.popup(cfg, QRect(100, 500, 300, 40))
    QTest.qWait(400)
    cfg["quotaApi"] = {
        "enabled": True,
        "showOnBar": True,
        "base": "bigmodel",
        "apiKey": "test",
        "source": "glm",
        "scope": "personal",
    }
    state = {
        "state": "ok",
        "ts": time.time(),
        "level": "pro",
        "windows": [{
            "kind": "tokens",
            "name": "5 小时窗口",
            "span_sec": 18000,
            "percent": 42.5,
            "used": 8.5,
            "total": 20.0,
            "reset_ms": 1730000000000,
        }],
        "cards": [{
            "id": "glm",
            "provider": "glm",
            "name": "GLM",
            "title": "GLM",
            "plan": "pro",
            "level": "pro",
            "windows": [{
                "kind": "tokens",
                "name": "5 小时窗口",
                "span_sec": 18000,
                "percent": 42.5,
                "used": 8.5,
                "total": 20.0,
            }],
        }],
        "row_updates": {},
    }

    for _ in range(15):
        panel.set_quota_state(state)
        QTest.qWait(30)
    n1 = len(panel.findChildren(QWidget))
    a1 = len(panel.findChildren(QPropertyAnimation))

    for _ in range(15):
        panel.set_quota_state(state)
        QTest.qWait(30)
    n2 = len(panel.findChildren(QWidget))
    a2 = len(panel.findChildren(QPropertyAnimation))

    print(f"重渲染两轮各 15 次: QWidget 子树数量 {n1} -> {n2} (应严格相等)", flush=True)
    assert n1 == n2, "重渲染路径产生 QWidget 子树泄漏！"
    print(f"重渲染两轮各 15 次: QPropertyAnimation 总数 {a1} -> {a2} (应严格相等)", flush=True)
    assert a1 == a2, "重渲染路径产生 QPropertyAnimation 泄漏！"

    panel.schedule_hide()
    QTest.qWait(700)
    flush()

    direct_anims = [a for a in panel.findChildren(QPropertyAnimation) if a.parent() is panel]
    print(f"面板直属短命动画残留: QPropertyAnimation={len(direct_anims)} (预期 0)", flush=True)
    assert not direct_anims, "面板直属弹出/隐藏动画对象仍在累积！"

    print("=== [5/5] SettingsDialog 多Tab与扩展插件配置收集验证 ===", flush=True)
    from app.gui.settings import SettingsDialog
    # 临时打桩 save_config 防测试落盘污染真实配置
    orig_save = config_mod.save_config
    config_mod.save_config = lambda c: None
    try:
        dlg = SettingsDialog(None, cfg)
        num_tabs = dlg._seg.count()
        assert num_tabs == 6, f"预期 6 个 Tab，实际 {num_tabs}"
        for i in range(num_tabs):
            dlg._seg.setCurrentIndex(i)
            dlg._on_seg_changed(i)
            assert dlg._stack.currentIndex() == i
        assert "system" in dlg._source_widgets, "system 数据源控件未挂载"
        dlg._source_widgets["system"]["interval"].setValue(5)
        dlg._collect_config()
        assert dlg.get_config().get("sources", {}).get("system", {}).get("intervalSec") == 5
        dlg.deleteLater()
        flush()
    finally:
        config_mod.save_config = orig_save

    print("VERIFY: OK (冒烟与防泄漏检查全部通过)", flush=True)


if __name__ == "__main__":
    run_smoke()
