"""tests/test_menu_position.py — 右键菜单避让任务栏定位计算与尺寸核验。"""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import QMenu

from app.core import config
from app.platform import win32_utils
from app.styles import theme
from app.gui.taskbar.widget import BarWidget, compute_menu_popup_pos


def test_bottom_taskbar_places_menu_above_taskbar():
    # 2560x1440 @175%，任务栏位于底部 y=[1356, 1440)，光标点击在任务栏内部 y=1400
    work_rect = (0, 0, 2560, 1356)
    tb_rect = (0, 1356, 2560, 1440)
    menu_w, menu_h = 360, 560
    gap = 14

    x, y = compute_menu_popup_pos(
        cursor_x=1900,
        cursor_y=1400,
        menu_w=menu_w,
        menu_h=menu_h,
        work_rect=work_rect,
        tb_rect=tb_rect,
        tb_edge="bottom",
        gap=gap,
        edge_pad=7,
    )

    assert x == 1900
    assert y + menu_h == tb_rect[1] - gap
    assert y + menu_h < tb_rect[1]
    assert y >= work_rect[1]


def test_bottom_taskbar_clamps_right_edge():
    work_rect = (0, 0, 1920, 1032)
    tb_rect = (0, 1032, 1920, 1080)
    menu_w, menu_h = 260, 380

    x, y = compute_menu_popup_pos(
        cursor_x=1850,
        cursor_y=1055,
        menu_w=menu_w,
        menu_h=menu_h,
        work_rect=work_rect,
        tb_rect=tb_rect,
        tb_edge="bottom",
        gap=8,
        edge_pad=4,
    )

    assert x + menu_w == work_rect[2] - 4
    assert y + menu_h == tb_rect[1] - 8


def test_top_taskbar_places_menu_below_taskbar():
    work_rect = (0, 48, 1920, 1080)
    tb_rect = (0, 0, 1920, 48)
    menu_w, menu_h = 240, 360

    x, y = compute_menu_popup_pos(
        cursor_x=1200,
        cursor_y=20,
        menu_w=menu_w,
        menu_h=menu_h,
        work_rect=work_rect,
        tb_rect=tb_rect,
        tb_edge="top",
        gap=8,
        edge_pad=4,
    )

    assert x == 1200
    assert y == tb_rect[3] + 8
    assert y >= tb_rect[3]
    assert y + menu_h <= work_rect[3]


def test_autohide_taskbar_still_avoids_tb_top():
    # 自动隐藏时 rcWork 可能覆盖全屏，但 tb_rect 仍标示任务栏当前位置
    work_rect = (0, 0, 1920, 1080)
    tb_rect = (0, 1032, 1920, 1080)
    menu_w, menu_h = 240, 360

    _, y = compute_menu_popup_pos(
        cursor_x=1200,
        cursor_y=1050,
        menu_w=menu_w,
        menu_h=menu_h,
        work_rect=work_rect,
        tb_rect=tb_rect,
        tb_edge="bottom",
        gap=8,
        edge_pad=4,
    )

    assert y + menu_h == 1032 - 8


def test_tall_menu_clamps_to_top_of_work_area():
    work_rect = (0, 0, 1920, 400)
    tb_rect = (0, 400, 1920, 448)

    _, y = compute_menu_popup_pos(
        cursor_x=500,
        cursor_y=420,
        menu_w=240,
        menu_h=500,
        work_rect=work_rect,
        tb_rect=tb_rect,
        tb_edge="bottom",
        gap=8,
        edge_pad=4,
    )

    assert y == 4


def test_bar_widget_menu_popup_pos_uses_taskbar_geometry(qapp, monkeypatch):
    cfg = config.load_config()
    bar = BarWidget(cfg)
    bar._scale = 1.75

    monkeypatch.setattr(win32_utils, "find_taskbar", lambda: 12345)
    monkeypatch.setattr(win32_utils, "get_rect", lambda hwnd: (0, 1356, 2560, 1440))
    monkeypatch.setattr(
        win32_utils,
        "get_monitor_info",
        lambda hwnd: (0, 0, 2560, 1440, 0, 0, 2560, 1356),
    )

    pos = bar._menu_popup_pos(QPoint(1800, 1400), 360, 520)
    gap = int(round(8 * 1.75))
    assert pos.x() == 1800
    assert pos.y() + 520 == 1356 - gap


def test_qmenu_measured_size_matches_popup_geometry(qapp):
    menu = QMenu()
    menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    scale = 1.75
    mf = QFont()
    mf.setFamilies(["Microsoft YaHei UI", "Segoe UI", "Segoe UI Emoji"])
    mf.setPixelSize(max(12, int(round(13 * scale))))
    mf.setWeight(QFont.Weight.Medium)
    menu.setFont(mf)
    menu.setStyleSheet(theme.menu_qss(False, scale))
    for label in ("暂停滚动", "开始专注 30 分钟", "编辑今日待办", "打开设置...", "退出"):
        menu.addAction(QAction(label, menu))

    menu.ensurePolished()
    menu.adjustSize()
    sz = menu.sizeHint()
    menu_w = max(sz.width(), menu.width())
    menu_h = max(sz.height(), menu.height())
    assert menu_w > 0 and menu_h > 0

    menu.popup(QPoint(100, 100))
    qapp.processEvents()
    geom = menu.geometry()
    menu.close()
    menu.deleteLater()

    assert abs(geom.width() - menu_w) <= 2
    assert abs(geom.height() - menu_h) <= 2


def test_compact_submenu_fits_content_without_excess_right_padding(qapp):
    from app.styles import tokens
    from app.gui import widgets as ui_parts
    scale = 1.75
    mf = QFont()
    mf.setFamilies(["Microsoft YaHei UI", "Segoe UI", "Segoe UI Emoji"])
    mf.setPixelSize(max(12, int(round(13 * scale))))
    mf.setWeight(QFont.Weight.Medium)
    icons = ui_parts.build_menu_icons(False, size=max(14, tokens.spx(15, scale)))

    # 真实父子结构：子菜单挂载在主菜单下，确保 compact 的 min-width: 0px 能覆盖父级 QSS 级联
    parent_menu = QMenu()
    parent_menu.setFont(mf)
    parent_menu.setStyleSheet(theme.menu_qss(False, scale, compact=False))

    submenu = QMenu("外观主题...", parent_menu)
    submenu.setFont(mf)
    submenu.setStyleSheet(theme.menu_qss(False, scale, compact=True))
    for k, label in (("auto", "跟随系统"), ("light", "浅色模式"), ("dark", "深色模式")):
        submenu.addAction(QAction(icons["check"] if k == "light" else icons["empty"], label, submenu))
    parent_menu.addMenu(submenu)

    submenu.ensurePolished()
    submenu.adjustSize()
    submenu.popup(QPoint(100, 100))
    qapp.processEvents()
    w = submenu.geometry().width()
    text_w = submenu.fontMetrics().horizontalAdvance("跟随系统")
    submenu.close()
    parent_menu.deleteLater()

    # 宽度应紧贴图标+文字+对称留白，不得继承父菜单的 min-width 导致右侧大片空白
    assert w > text_w
    assert w <= int(round(112 * scale))
