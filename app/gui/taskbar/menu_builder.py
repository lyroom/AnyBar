"""app/gui/taskbar/menu_builder.py — 任务栏右键菜单建造者（Builder 模式 + 任务栏避让定位）"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QCursor, QFont, QGuiApplication
from PySide6.QtWidgets import QMenu

from app.core import config as config_mod
from app.gui import widgets as ui_parts
from app.platform import autostart, glass, win32_utils
from app.styles import theme, tokens

from .views import VIEW_LABELS

if TYPE_CHECKING:
    from .widget import BarWidget


def compute_menu_popup_pos(
    cursor_x: int,
    cursor_y: int,
    menu_w: int,
    menu_h: int,
    work_rect: tuple[int, int, int, int],
    tb_rect: tuple[int, int, int, int] | None = None,
    tb_edge: str = "bottom",
    gap: int = 8,
    edge_pad: int = 4,
) -> tuple[int, int]:
    """计算右键菜单弹出左上角坐标（物理像素），严格避开任务栏并防止超出工作区边界。

    work_rect / tb_rect 均为 Win32 风格 (left, top, right, bottom) 坐标。
    """
    wl, wt, wr, wb = work_rect
    menu_w = max(0, int(menu_w))
    menu_h = max(0, int(menu_h))
    gap = max(0, int(gap))
    edge_pad = max(0, int(edge_pad))

    if wr - wl <= menu_w + edge_pad * 2:
        x = wl
    else:
        x = max(wl + edge_pad, min(int(cursor_x), wr - menu_w - edge_pad))

    if tb_edge == "top":
        top_limit = max(wt, tb_rect[3]) if tb_rect else wt
        y = top_limit + gap
        if y + menu_h > wb - edge_pad:
            y = max(top_limit, wb - menu_h - edge_pad)
    else:
        bottom_limit = min(wb, tb_rect[1]) if tb_rect else wb
        y = bottom_limit - menu_h - gap
        if y < wt + edge_pad:
            y = wt + edge_pad

    return int(x), int(y)


def resolve_menu_popup_pos(scale: float, cursor_pos: QPoint, menu_w: int, menu_h: int) -> QPoint:
    """结合真实任务栏与屏幕工作区计算菜单弹出坐标，避免菜单底部落入任务栏被遮挡。"""
    s = max(1.0, float(scale or theme.screen_scale()))
    gap = max(6, int(round(8 * s)))
    edge_pad = max(4, int(round(4 * s)))

    tb_rect = None
    tb_edge = "bottom"
    work_rect = None

    taskbar = win32_utils.find_taskbar()
    if taskbar:
        tb_rect = win32_utils.get_rect(taskbar)
        mon = win32_utils.get_monitor_info(taskbar)
        if mon:
            work_rect = (mon[4], mon[5], mon[6], mon[7])
        if tb_rect and mon:
            tb_edge = win32_utils.get_taskbar_edge(tb_rect, mon)

    if work_rect is None:
        screen = QGuiApplication.screenAt(cursor_pos) or QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            work_rect = (
                avail.left(),
                avail.top(),
                avail.left() + avail.width(),
                avail.top() + avail.height(),
            )
        else:
            work_rect = (0, 0, 1920, 1080)

    x, y = compute_menu_popup_pos(
        cursor_pos.x(),
        cursor_pos.y(),
        menu_w,
        menu_h,
        work_rect=work_rect,
        tb_rect=tb_rect,
        tb_edge=tb_edge,
        gap=gap,
        edge_pad=edge_pad,
    )
    return QPoint(x, y)


def _round_menu_corners(menu: QMenu) -> None:
    try:
        hwnd = int(menu.winId())
        if hwnd:
            glass.round_corners(hwnd)
    except Exception:
        pass


class BarContextMenuBuilder:
    """常驻条右键菜单建造者：组装分组菜单、应用独立 menu.qss 并保证生命周期零泄漏。"""

    def __init__(self, bar: BarWidget) -> None:
        self._bar = bar

    def build(self) -> QMenu:
        bar = self._bar
        dark = theme.is_system_dark()
        scale = bar._scale

        menu = QMenu(bar)
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        mf = QFont()
        mf.setFamilies(["Microsoft YaHei UI", "Segoe UI", "Segoe UI Emoji"])
        mf.setPixelSize(max(12, int(round(13 * scale))))
        mf.setWeight(QFont.Weight.Medium)
        mf.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        menu.setFont(mf)
        menu.setStyleSheet(theme.menu_qss(dark, scale))

        ic_sz = max(14, tokens.spx(15, scale))
        menu_icons = ui_parts.build_menu_icons(dark, size=ic_sz)

        self._add_view_submenu(menu, mf, menu_icons, dark, scale)
        self._add_daily_actions(menu, menu_icons)
        menu.addSeparator()
        self._add_appearance_and_mode_actions(menu, mf, menu_icons, dark, scale)
        menu.addSeparator()
        self._add_system_actions(menu, menu_icons)

        try:
            menu.aboutToShow.connect(lambda m=menu: _round_menu_corners(m))
        except Exception:
            pass
        return menu

    def _add_view_submenu(self, menu: QMenu, mf: QFont, menu_icons: dict, dark: bool, scale: float) -> None:
        bar = self._bar
        avail_views = bar.available_views()
        cur_v = bar.current_view()
        if len(avail_views) <= 1:
            return
        view_menu = menu.addMenu(menu_icons["switch"], "常驻视图...")
        view_menu.setFont(mf)
        view_menu.setStyleSheet(theme.menu_qss(dark, scale, compact=True))
        try:
            view_menu.aboutToShow.connect(lambda m=view_menu: _round_menu_corners(m))
        except Exception:
            pass
        for v_key in avail_views:
            v_title = VIEW_LABELS.get(v_key, v_key)
            is_cur = v_key == cur_v
            act_v = QAction(menu_icons["check"] if is_cur else menu_icons["empty"], v_title, view_menu)
            act_v.triggered.connect(lambda _c=False, vk=v_key: bar.toggle_view(target_view=vk))
            view_menu.addAction(act_v)
        view_menu.addSeparator()
        act_next = QAction(menu_icons["rotate"], "轮转下一个视图 (可双击常驻条)", view_menu)
        act_next.triggered.connect(lambda: bar.toggle_view())
        view_menu.addAction(act_next)

    def _add_daily_actions(self, menu: QMenu, menu_icons: dict) -> None:
        bar = self._bar
        pause_text = "恢复滚动" if bar._paused else "暂停滚动"
        pause_icon = menu_icons["play"] if bar._paused else menu_icons["pause"]
        act_pause = QAction(pause_icon, pause_text, menu)
        act_pause.triggered.connect(bar.toggle_pause)

        in_focus = bar._focus_until and time.monotonic() < bar._focus_until
        focus_text = "退出专注模式" if in_focus else "开始专注 30 分钟"
        act_focus = QAction(menu_icons["focus"], focus_text, menu)
        act_focus.triggered.connect(lambda: bar.toggle_focus(30))

        act_edit = QAction(menu_icons["todo"], "编辑今日待办", menu)
        act_edit.triggered.connect(bar.request_edit_todos.emit)

        menu.addAction(act_pause)
        menu.addAction(act_focus)
        menu.addAction(act_edit)

    def _add_appearance_and_mode_actions(
        self, menu: QMenu, mf: QFont, menu_icons: dict, dark: bool, scale: float
    ) -> None:
        bar = self._bar
        theme_menu = QMenu("外观主题...", menu)
        theme_menu.setIcon(menu_icons["theme"])
        theme_menu.setFont(mf)
        theme_menu.setStyleSheet(theme.menu_qss(dark, scale, compact=True))
        try:
            theme_menu.aboutToShow.connect(lambda m=theme_menu: _round_menu_corners(m))
        except Exception:
            pass
        cur_tm = str(bar._cfg.get("style", {}).get("themeMode", "auto") or "auto")
        for tm_key, tm_label in (("auto", "跟随系统"), ("light", "浅色模式"), ("dark", "深色模式")):
            act_tm = QAction(menu_icons["check"] if cur_tm == tm_key else menu_icons["empty"], tm_label, theme_menu)
            act_tm.triggered.connect(lambda _c=False, mk=tm_key: bar._select_theme_mode(mk))
            theme_menu.addAction(act_tm)

        act_capsule = QAction(menu_icons["capsule"], "微型双列胶囊模式", menu)
        act_capsule.setCheckable(True)
        act_capsule.setChecked(bar.is_capsule_mode())

        def _toggle_capsule_mode(checked: bool):
            bar._cfg["style"]["displayMode"] = "capsule" if checked else "full"
            config_mod.save_config(bar._cfg)
            bar.set_capsule_collapsed(checked)
            bar.content_width_changed.emit(bar.desired_width())

        act_capsule.triggered.connect(_toggle_capsule_mode)

        act_autostart = QAction(menu_icons["launch"], "开机自启动", menu)
        act_autostart.setCheckable(True)
        act_autostart.setChecked(autostart.is_enabled())
        act_autostart.triggered.connect(lambda checked: autostart.enable() if checked else autostart.disable())

        menu.addMenu(theme_menu)
        menu.addAction(act_capsule)
        menu.addAction(act_autostart)

    def _add_system_actions(self, menu: QMenu, menu_icons: dict) -> None:
        bar = self._bar
        act_refresh = QAction(menu_icons["refresh"], "立即刷新", menu)
        act_refresh.triggered.connect(bar._on_user_refresh)
        act_settings = QAction(menu_icons["settings"], "打开设置...", menu)
        act_settings.triggered.connect(bar.request_settings.emit)
        act_quit = QAction(menu_icons["quit"], "退出", menu)
        act_quit.triggered.connect(bar.request_quit.emit)

        menu.addAction(act_refresh)
        menu.addAction(act_settings)
        menu.addSeparator()
        menu.addAction(act_quit)

    def show_at_cursor(self) -> None:
        bar = self._bar
        menu = self.build()
        menu.ensurePolished()
        menu.adjustSize()
        sz = menu.sizeHint()
        menu_w = max(sz.width(), menu.width())
        menu_h = max(sz.height(), menu.height())
        popup_pos = bar._menu_popup_pos(QCursor.pos(), menu_w, menu_h)
        bar.menu_about_to_show.emit()
        menu.exec(popup_pos)
        bar.menu_closed.emit()
        # 短命 QMenu 以 bar 为 parent，必须 deleteLater 防对象累积泄漏
        menu.deleteLater()
