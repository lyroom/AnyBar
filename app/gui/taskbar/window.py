from PySide6.QtCore import QEasingCurve, QRect, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QCursor, QFont, QGuiApplication
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

import time

from app.platform import glass
from app.styles import theme
from app.platform import win32_utils
from app.core import config as config_mod
from .widget import BarWidget
from app.gui.hover_panel import HoverPanel
from app.core.quota_api import QuotaService
from app.core.source_service import SourceService

REPOSITION_INTERVAL_MS = 500
UIA_RECHECK_SEC = 60.0  # 空闲兜底周期（平时由 WinEvent/几何突变驱动，空闲时避免频繁起 PowerShell 子进程）
UIA_UPDATE_THRESHOLD = 16

EDGE_MARGIN = 2

import os
import threading

from app.core.logger import get_logger


import logging

_RP_DEBUG_TAGS = {"snap", "deadzone", "color"}


def _rp_log(tag, **kw):
    is_debug = tag in _RP_DEBUG_TAGS
    if is_debug:
        if not _rp_logger.isEnabledFor(logging.DEBUG):
            return
    elif not _rp_logger.isEnabledFor(logging.INFO):
        return
    parts = [tag]
    for k, v in kw.items():
        parts.append(f"{k}={v}")
    msg = " ".join(str(p) for p in parts)
    if is_debug:
        _rp_logger.debug(msg)
    else:
        _rp_logger.info(msg)


_rp_logger = get_logger("anybar.reposition", "reposition.log", env_var="TOUCHBAR_LOG")


class TaskbarWindow(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._cfg = cfg
        theme.apply_theme_mode_from_cfg(cfg)
        self._bar = BarWidget(cfg, self)
        self._panel = HoverPanel()
        self._last_dark = theme.is_system_dark()
        self._hidden_by_fullscreen = False
        self._shrunk = False
        self._uia_icon_right = None
        self._uia_tick = 0
        self._uia_busy = False
        self._last_uia_time = 0.0
        self._menu_open = False
        self._embedded = False
        self._capsule_expanded = False
        self._expand_anim = None
        if self._bar.is_capsule_mode():
            self._bar._capsule_collapsed = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._bar)

        # 优先初始化数据源并连接信号，重放本地硬件初始状态，确保首帧测宽与悬浮窗即刻具备数据
        self._source_service = SourceService(cfg, parent=self)
        self._quota_service = self._source_service
        self._source_service.updated.connect(self._on_source_state)
        self._source_service.replay_states()

        self._desired_w = self._bar.desired_width()
        self._bar.content_width_changed.connect(self._on_bar_width_changed)

        self._reposition_timer = QTimer(self)
        self._reposition_timer.setInterval(REPOSITION_INTERVAL_MS)
        self._reposition_timer.timeout.connect(self.reposition)

        self.apply_panel_font()
        cached = config_mod.load_uia_cache()
        if cached:
            self._uia_icon_right = cached
        if self._uia_icon_right is None:
            self._prime_uia_blocking()
        self.apply_bg()
        self.reposition()
        self._reposition_timer.start()
        if not self.isVisible():
            self.show()
        self._hwnd = int(self.winId())
        self._try_embed_taskbar()
        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(300)
        self._topmost_timer.timeout.connect(self._keep_topmost)
        self._topmost_timer.start()

        # 低频空闲垃圾回收（10 分钟一次），在完全空闲窗口平滑回收循环引用与解除对象碎片
        self._idle_gc_timer = QTimer(self)
        self._idle_gc_timer.setInterval(10 * 60 * 1000)
        self._idle_gc_timer.timeout.connect(self._run_idle_gc)
        self._idle_gc_timer.start()
        self._bar.menu_about_to_show.connect(self._on_menu_open)
        self._bar.menu_closed.connect(self._on_menu_close)
        self._bar.paint_stalled.connect(self._recover_paint)
        self._bar.request_refresh.connect(self._on_user_request_refresh)
        self._bar.theme_mode_changed.connect(self._on_theme_mode_changed)
        self._panel.todo_toggled.connect(self._recv_panel_toggle)
        self._panel.todo_added.connect(self._recv_panel_add_todo)
        self._panel.todos_cleared.connect(self._recv_panel_clear_done)
        self._panel.panel_hidden.connect(self._on_panel_hidden)
        try:
            QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_scheme_changed)
        except (AttributeError, RuntimeError):
            pass

        self._last_event_reposition = 0.0
        win32_utils.install_winevent_hook(self._on_winevent)

    def _keep_topmost(self):
        if os.environ.get("TOUCHBAR_NO_TOPMOST"):
            return
        if not self.isVisible() or self._menu_open:
            return
        if self._embedded:
            if getattr(self, "_host_hwnd", 0):
                win32_utils.set_topmost_flag_child(self._host_hwnd)
        else:
            win32_utils.set_topmost_flag(self._hwnd)

    def reposition(self, force: bool = False):
        if getattr(self, "_expand_anim", None) is not None and self._expand_anim.state() == QVariantAnimation.State.Running:
            return
        if self._panel.isVisible() and getattr(self._panel, "_input_focused", False):
            return
        if win32_utils.get_foreground_class() == "TopLevelWindowForOverflowXamlIsland":
            return
        dpr = win32_utils.get_system_dpi() / 96
        taskbar = win32_utils.find_taskbar()
        if not taskbar:
            return
        tb = win32_utils.get_rect(taskbar)
        if not tb:
            return
        tb_left, tb_top = tb[0], tb[1]
        tb_right = tb[2]
        tb_h = tb[3] - tb_top

        mon = win32_utils.get_monitor_info(taskbar)
        if mon:
            sw_phys = mon[2] - mon[0]
            sh_phys = mon[3] - mon[1]
        else:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.geometry()
                sw_phys = int(geo.width() * dpr)
                sh_phys = int(geo.height() * dpr)
            else:
                sw_phys = tb_right - tb_left
                sh_phys = tb_h
        _fs = win32_utils.is_fullscreen_active(sw_phys, sh_phys)
        _ah = win32_utils.taskbar_auto_hidden(tb, sw_phys, sh_phys)
        if _fs or _ah:
            _fgh = win32_utils.get_foreground_window()
            _fgcls = win32_utils.get_foreground_class()
            _fgr = win32_utils.get_rect(_fgh) if _fgh else None
            _rp_log("HIDE", fs=_fs, autohide=_ah, vis=self.isVisible(), tb=tb,
                    fgcls=_fgcls, fgrect=_fgr, screen=f"{sw_phys}x{sh_phys}")
            if self.isVisible():
                self._hidden_by_fullscreen = True
                self.hide()
                self._bar.suspend_animations()
            return
        if self._hidden_by_fullscreen:
            self._hidden_by_fullscreen = False
            self._bar.resume_animations()

        edge = win32_utils.get_taskbar_edge(tb, mon)
        if edge in ("left", "right"):
            return

        tray = win32_utils.find_tray_notify(taskbar)
        tray_left_phys = tb_right
        if tray:
            tr = win32_utils.get_rect(tray)
            if tr:
                tray_left_phys = tr[0]
        right_phys = tray_left_phys - int(6 * dpr)

        hwnd = int(self.winId())
        rebar = win32_utils.find_window_by_class(taskbar, "ReBarWindow32")
        rebar_right = 0
        if rebar:
            rr = win32_utils.get_rect(rebar)
            if rr and rr[2] < tray_left_phys:
                rebar_right = rr[2]

        now = time.monotonic()
        layout_changed = (rebar_right != getattr(self, "_last_rebar_right", -1)
                          or tray_left_phys != getattr(self, "_last_tray_left", -1)
                          or now - getattr(self, "_layout_event_ts", 0.0) < 1.0)
        self._last_rebar_right = rebar_right
        self._last_tray_left = tray_left_phys
        if not self._hidden_by_fullscreen and (self._uia_icon_right is None or layout_changed
                or now - self._last_uia_time > UIA_RECHECK_SEC) and not self._uia_busy:
            self._uia_busy = True
            self._last_uia_time = now

            def _uia_worker():
                try:
                    best = None
                    for attempt in range(2):
                        if win32_utils.get_foreground_class() == "TopLevelWindowForOverflowXamlIsland":
                            break
                        v = win32_utils.find_icon_right_edge_uia(tray_left_phys, rebar_right)
                        if v and rebar_right < v < tray_left_phys:
                            best = v
                            break  # 单次探测成功直接收敛，避免连开多轮 PowerShell 子进程
                        if attempt == 0:
                            time.sleep(0.2)
                    if best is not None:
                        config_mod.save_uia_cache(best)
                        if self._uia_icon_right is None:
                            self._uia_icon_right = best
                        elif abs(best - self._uia_icon_right) >= UIA_UPDATE_THRESHOLD:
                            pend = getattr(self, "_uia_pending", None)
                            if pend is not None and abs(best - pend) < UIA_UPDATE_THRESHOLD:
                                self._uia_icon_right = best
                                self._uia_pending = None
                            else:
                                self._uia_pending = best
                        else:
                            self._uia_pending = None
                finally:
                    self._uia_busy = False
            threading.Thread(target=_uia_worker, daemon=True).start()

        if self._uia_icon_right and self._uia_icon_right < tray_left_phys:
            left_limit_phys = self._uia_icon_right + int(6 * dpr)
        else:
            left_limit_phys = rebar_right + int(6 * dpr)

        cfg_w = int(self._cfg["style"].get("width", 330))
        if self._bar.is_tiles_view():
            cfg_w = max(cfg_w, 420)
        configured_width = int(cfg_w * dpr)
        locked_width = self._desired_w if self._desired_w else configured_width
        min_w_phys = int(80 * dpr)
        dead_zone = int(8 * dpr)
        hysteresis = int(20 * dpr)
        if left_limit_phys > right_phys - min_w_phys:
            left_limit_phys = right_phys - min_w_phys
        avail_phys = right_phys - left_limit_phys
        _rp_log("snap", vis=self.isVisible(), trayL=tray_left_phys, rebarR=rebar_right,
                uiaR=self._uia_icon_right, leftLim=left_limit_phys, right=right_phys,
                avail=avail_phys, shrunk=self._shrunk, cfgW=locked_width)

        if self._shrunk:
            if avail_phys >= locked_width + hysteresis:
                self._shrunk = False
                target_w = locked_width
            else:
                target_w = max(min_w_phys, avail_phys - int(8 * dpr))
        elif avail_phys >= locked_width:
            target_w = locked_width
        else:
            self._shrunk = True
            target_w = max(min_w_phys, avail_phys - int(8 * dpr))
        target_w = max(min_w_phys, target_w)

        _margin = int(EDGE_MARGIN * dpr)
        _expect_x = right_phys - target_w - tb_left if self._embedded else right_phys - target_w
        _expect_y = _margin if self._embedded else tb_top + _margin
        native = win32_utils.get_rect(hwnd)
        current_w = (native[2] - native[0]) if native else self.width()
        if native:
            pos_drift = (abs(native[0] - (right_phys - target_w)) > 2
                         or abs(native[1] - (tb_top + _margin)) > 2)
        else:
            pos_drift = abs(self.x() - _expect_x) > 2 or abs(self.y() - _expect_y) > 2
        if not force and self.isVisible() and abs(target_w - current_w) < dead_zone and not pos_drift:
            _rp_log("deadzone", target=target_w, cur=current_w, vis=self.isVisible())
            if (now - getattr(self, "_color_sample_ts", 0.0) > 2.0
                    and not self._panel.isVisible() and not self._menu_open):
                self._color_sample_ts = now
                if native:
                    bx, by = native[0], native[1]
                elif self._embedded:
                    bx, by = self.x() + tb_left, self.y() + tb_top
                else:
                    bx, by = self.x(), self.y()
                rgb = win32_utils.sample_taskbar_bg_color((bx, by, bx + self.width(), by + self.height()))
                _rp_log("color", rgb=rgb, bx=bx, by=by)
                if rgb:
                    self._bar.set_taskbar_color(rgb)
            if not self._embedded:
                win32_utils.set_topmost_flag(hwnd)
            return

        final_w_phys = target_w

        x_phys = right_phys - final_w_phys
        if left_limit_phys < right_phys and x_phys < left_limit_phys:
            x_phys = left_limit_phys
        if x_phys < tb_left:
            x_phys = tb_left
        if x_phys + final_w_phys > right_phys:
            final_w_phys = max(min_w_phys, right_phys - x_phys)
            x_phys = right_phys - final_w_phys

        margin_phys = int(EDGE_MARGIN * dpr)
        final_h_phys = tb_h - margin_phys * 2
        y_phys = tb_top + margin_phys

        if not self._bar.is_capsule_mode():
            self._bar.set_compact(False)

        if not self.isVisible():
            self.show()
        self.setGeometry(x_phys, y_phys, final_w_phys, final_h_phys)
        if self._embedded:
            win32_utils.invalidate_taskbar(taskbar)
        else:
            win32_utils.set_topmost_flag(hwnd)
        _rp_log("MOVE", x=x_phys, y=y_phys, w=final_w_phys, h=final_h_phys, vis=self.isVisible())
        self.update()
        self._bar._swp_frame(time.monotonic())

    def _try_embed_taskbar(self):
        taskbar = win32_utils.find_taskbar()
        if not taskbar:
            return
        try:
            r = win32_utils.get_rect(self._hwnd)
            tb_r = win32_utils.get_rect(taskbar)
            if not r or not tb_r:
                return
            mon = win32_utils.get_monitor_info(taskbar)
            if mon:
                sw = mon[2] - mon[0]
                sh = mon[3] - mon[1]
            else:
                dpr = win32_utils.get_system_dpi() / 96
                screen = QApplication.primaryScreen()
                geo = screen.geometry() if screen else None
                sw = int(geo.width() * dpr) if geo else tb_r[2] - tb_r[0]
                sh = int(geo.height() * dpr) if geo else tb_r[3] - tb_r[1]
            host = getattr(self, "_host_hwnd", 0)
            if not host:
                host = win32_utils.create_taskbar_host(
                    taskbar, -tb_r[0], -tb_r[1], sw, sh)
                if not host:
                    return
                self._host_hwnd = host
            else:
                win32_utils.move_host_window(host, -tb_r[0], -tb_r[1], sw, sh)
            style = win32_utils.user32.GetWindowLongW(
                self._hwnd, win32_utils.GWL_STYLE)
            win32_utils.user32.SetWindowLongW(
                self._hwnd, win32_utils.GWL_STYLE,
                (style & ~win32_utils.WS_POPUP) | win32_utils.WS_CHILD)
            ex = win32_utils.user32.GetWindowLongW(
                self._hwnd, win32_utils.GWL_EXSTYLE)
            win32_utils.user32.SetWindowLongW(
                self._hwnd, win32_utils.GWL_EXSTYLE,
                ex | win32_utils.WS_EX_TOOLWINDOW | win32_utils.WS_EX_NOACTIVATE)
            win32_utils.user32.SetParent(self._hwnd, host)
            self._embedded = True
            win32_utils.set_topmost_flag_child(host)
            self.setGeometry(r[0], r[1], r[2] - r[0], r[3] - r[1])
            _rp_log("embed", host=host, pos=(r[0], r[1]),
                    host_at=(-tb_r[0], -tb_r[1]), size=(sw, sh))
        except OSError as e:
            _rp_log("embederr", err=repr(e)[:120])

    def _prime_uia_blocking(self):
        result = []

        def _first_shot():
            try:
                if win32_utils.get_foreground_class() == "TopLevelWindowForOverflowXamlIsland":
                    return
                taskbar = win32_utils.find_taskbar()
                if not taskbar:
                    return
                tb = win32_utils.get_rect(taskbar)
                if not tb:
                    return
                tray_left = tb[2]
                tray = win32_utils.find_tray_notify(taskbar)
                if tray:
                    tr = win32_utils.get_rect(tray)
                    if tr:
                        tray_left = tr[0]
                rebar = win32_utils.find_window_by_class(taskbar, "ReBarWindow32")
                rebar_right = 0
                if rebar:
                    rr = win32_utils.get_rect(rebar)
                    if rr and rr[2] < tray_left:
                        rebar_right = rr[2]
                v = win32_utils.find_icon_right_edge_uia(tray_left, rebar_right)
                if v and rebar_right < v < tray_left:
                    result.append(v)
                    self._uia_icon_right = v
                    self._last_uia_time = time.monotonic()
                    config_mod.save_uia_cache(v)
            finally:
                self._uia_busy = False

        self._uia_busy = True
        t = threading.Thread(target=_first_shot, daemon=True)
        t.start()
        t.join(timeout=3.0)
        ok = bool(result)
        if not ok:
            self._last_uia_time = 0.0
        _rp_log("prime", ok=ok, got=result[0] if result else None)

    def _on_scheme_changed(self, scheme):
        dark = theme.is_system_dark()
        if dark != self._last_dark:
            self._last_dark = dark
            self._bar.apply_style()
            if self._panel.isVisible():
                self._panel.popup(self._cfg, self._anchor_rect())

    def _on_theme_mode_changed(self, _mode: str):
        self._last_dark = theme.is_system_dark()
        self._bar.apply_style()
        if self._panel.isVisible():
            self._panel.popup(self._cfg, self._anchor_rect())

    def _on_todo_toggled(self):
        from app.core import config as config_mod
        config_mod.save_config(self._cfg)
        self._bar.refresh_content()

    def _recv_panel_toggle(self, index, checked):
        todos = self._cfg.get("todos", [])
        if 0 <= index < len(todos):
            todos[index]["done"] = checked
        self._on_todo_toggled()

    def _recv_panel_clear_done(self):
        from app.core import config as config_mod
        todos = self._cfg.get("todos", [])
        if isinstance(todos, list):
            todos[:] = [t for t in todos
                        if not (isinstance(t, dict) and t.get("done"))]
        config_mod.save_config(self._cfg)
        self._bar.refresh_content()
        if not self._panel.sync_todos_inplace(self._cfg, self._anchor_rect(), keep_focus=False):
            if self._panel.isVisible():
                self._panel.popup(self._cfg, self._anchor_rect())

    def _recv_panel_add_todo(self, text: str):
        import datetime
        from app.core import config as config_mod
        now = datetime.datetime.now()
        self._cfg.setdefault("todos", []).append({
            "time": now.strftime("%H:%M"),
            "title": text,
            "note": "",
            "done": False,
        })
        config_mod.save_config(self._cfg)
        self._bar.refresh_content()
        if not self._panel.sync_todos_inplace(self._cfg, self._anchor_rect(), keep_focus=True):
            if self._panel.isVisible():
                self._panel.popup(self._cfg, self._anchor_rect())

    def _on_user_request_refresh(self):
        if getattr(self, "_source_service", None) is not None:
            self._source_service.refresh()

    def _recover_paint(self):
        new_hwnd = int(self.winId())
        if new_hwnd and new_hwnd != self._hwnd:
            self._hwnd = new_hwnd
            self._try_embed_taskbar()
        self.reposition()
        _rp_log("recover", hwnd=self._hwnd)

    def _on_menu_open(self):
        self._menu_open = True
        self._panel.close_now()

    def _on_menu_close(self):
        self._menu_open = False

    def _on_panel_hidden(self):
        self._color_sample_ts = 0.0
        if self._bar.is_capsule_mode() and getattr(self, "_capsule_expanded", False):
            g_pos = QCursor.pos()
            r = self._anchor_rect()
            if not r.contains(g_pos):
                self._capsule_expanded = False
                self._animate_capsule(expand=False)

    def _on_bar_width_changed(self, w: int):
        if w:
            old_w = self._desired_w
            need_reposition = (w != old_w)
            self._desired_w = w
            if (need_reposition and self.isVisible() and not self._bar.is_capsule_mode()
                    and not self._shrunk and old_w and abs(w - self.width()) >= 6
                    and (getattr(self, "_expand_anim", None) is None
                         or self._expand_anim.state() != QVariantAnimation.State.Running)):
                self._animate_width_to(w)
            else:
                self.reposition(force=need_reposition)

    def _animate_width_to(self, target_w: int):
        """切换视图时右侧锚定平滑过渡常驻条宽度，避免宽度瞬间跳变。"""
        taskbar = win32_utils.find_taskbar()
        if not taskbar:
            self.reposition(force=True)
            return
        dpr = win32_utils.get_system_dpi() / 96
        tray = win32_utils.find_tray_notify(taskbar)
        tb = win32_utils.get_rect(taskbar)
        if not tb:
            self.reposition(force=True)
            return
        tray_left_phys = tb[2]
        if tray:
            tr = win32_utils.get_rect(tray)
            if tr:
                tray_left_phys = tr[0]
        right_phys = tray_left_phys - int(6 * dpr)
        rebar = win32_utils.find_window_by_class(taskbar, "ReBarWindow32")
        rebar_right = 0
        if rebar:
            rr = win32_utils.get_rect(rebar)
            if rr and rr[2] < tray_left_phys:
                rebar_right = rr[2]
        if self._uia_icon_right and self._uia_icon_right < tray_left_phys:
            left_limit_phys = self._uia_icon_right + int(6 * dpr)
        else:
            left_limit_phys = rebar_right + int(6 * dpr)
        min_w_phys = int(80 * dpr)
        avail_phys = max(min_w_phys, right_phys - left_limit_phys)
        end_w = max(min_w_phys, min(int(target_w), avail_phys))
        start_w = self.width()
        if abs(end_w - start_w) < 4:
            self.reposition(force=True)
            return

        if getattr(self, "_expand_anim", None) is not None:
            self._expand_anim.stop()
            self._expand_anim.deleteLater()
            self._expand_anim = None

        self._expand_anim = QVariantAnimation(self)
        self._expand_anim.setDuration(200)
        self._expand_anim.setStartValue(start_w)
        self._expand_anim.setEndValue(end_w)
        self._expand_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        anchor_right = self.x() + start_w

        def _step(val):
            w_cur = int(val)
            x_cur = anchor_right - w_cur
            self.setGeometry(x_cur, self.y(), w_cur, self.height())
            self._bar._swp_frame(time.monotonic())

        def _finished():
            if getattr(self, "_expand_anim", None) is not None:
                self._expand_anim.deleteLater()
                self._expand_anim = None
            self.reposition(force=True)

        self._expand_anim.valueChanged.connect(_step)
        self._expand_anim.finished.connect(_finished)
        self._expand_anim.start()

    def _open_edit_todos(self):
        self._panel.popup(self._cfg, self._anchor_rect())
        if hasattr(self._panel, "_add_input") and self._panel._add_input.isVisible():
            self._panel._add_input.setFocus()

    def _on_winevent(self, *args):
        now = time.monotonic()
        ev = args[1] if len(args) > 1 else 0
        if ev in (0x8002, 0x8004):
            self._layout_event_ts = now
        if now - self._last_event_reposition < 0.2:
            return
        self._last_event_reposition = now
        QTimer.singleShot(0, self.reposition)

    def _run_idle_gc(self):
        # 仅在非悬停、面板隐藏且非菜单打开等完全空闲时刻执行，彻底避免任何动画帧顿挫
        if self._panel.isVisible() or self._menu_open or getattr(self._bar, "_hover", False):
            return
        import gc
        gc.collect()

    def shutdown(self):
        """退出前拆嵌入：先摘条窗再销毁 Host，避免系统连带外部销毁 Qt 窗口。

        app.quit() 不经过 closeEvent，须由 aboutToQuit 兜底调用；幂等。
        """
        source_service = getattr(self, "_source_service", None)
        if source_service is not None:
            source_service.shutdown()
        win32_utils.uninstall_winevent_hook()
        for timer in (getattr(self, "_reposition_timer", None),
                      getattr(self, "_topmost_timer", None),
                      getattr(self, "_idle_gc_timer", None)):
            if timer is not None:
                timer.stop()
        if getattr(self, "_expand_anim", None) is not None:
            self._expand_anim.stop()
            self._expand_anim.deleteLater()
            self._expand_anim = None
        panel = getattr(self, "_panel", None)
        if panel is not None:
            panel.close_now()
        host = getattr(self, "_host_hwnd", 0)
        hwnd = getattr(self, "_hwnd", 0)
        if host and hwnd:
            try:
                win32_utils.detach_from_host(hwnd)
            except OSError:
                pass
        if host:
            try:
                win32_utils.destroy_host_window(host)
            except OSError:
                pass
            self._host_hwnd = 0
        self._embedded = False

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._bar.refresh_content()

    def apply_config(self, cfg: dict):
        if cfg is not self._cfg:
            self._cfg.clear()
            self._cfg.update(cfg)
        theme.apply_theme_mode_from_cfg(self._cfg)
        self._last_dark = theme.is_system_dark()
        self._bar.set_config(self._cfg)
        self._source_service.configure(self._cfg)
        self.apply_panel_font()
        self.apply_bg()
        self.reposition()
        if self._panel.isVisible():
            self._panel.popup(self._cfg, self._anchor_rect())

    def _on_source_state(self, state: dict):
        """数据源更新统一派发：将各源 tiles 派发给条与面板，兼容处理 quota 状态。"""
        s_id = str(state.get("source") or "")
        tiles = state.get("tiles")
        if tiles is not None:
            self._bar.set_source_tiles(s_id, tiles)
            if s_id != "quota":
                self._panel.set_source_tiles(s_id, tiles)
        if s_id == "quota" or "cards" in state or "row_updates" in state:
            self._on_quota_state(state)

    def _on_quota_state(self, state: dict):
        """余额查询结果：条（额度视图合成项）与悬停面板卡片同步更新，并将最新数值回填到内存套餐项。"""
        row_updates = (state or {}).get("row_updates") or {}
        quotas = self._cfg.get("quotas")
        if isinstance(quotas, list) and row_updates:
            for idx, upd in row_updates.items():
                if isinstance(idx, int) and 0 <= idx < len(quotas) and isinstance(upd, dict):
                    q = quotas[idx]
                    if isinstance(q, dict):
                        for k in ("used", "limit", "unit", "balance", "status"):
                            if upd.get(k) is not None:
                                q[k] = upd[k]
        self._bar.set_quota_state(state)
        self._panel.set_quota_state(state)

    def apply_bg(self):
        hwnd = int(self.winId())
        if hwnd:
            glass.round_corners(hwnd)

    def bar(self) -> BarWidget:
        return self._bar

    def _anchor_rect(self) -> QRect:
        hwnd = int(self.winId())
        r = win32_utils.get_rect(hwnd)
        if r:
            return QRect(r[0], r[1], r[2] - r[0], r[3] - r[1])
        return self.geometry()

    def enterEvent(self, event):
        self._bar.set_hover(True)
        if self._bar.is_capsule_mode():
            if not self._capsule_expanded:
                self._capsule_expanded = True
                self._animate_capsule(expand=True)
            elif not self._menu_open and not self._panel.isVisible():
                self._panel.popup(self._cfg, self._anchor_rect())
        else:
            if not self._menu_open and not self._panel.isVisible():
                self._panel.popup(self._cfg, self._anchor_rect())
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._bar.set_hover(False)
        self._panel.schedule_hide()
        if self._bar.is_capsule_mode() and self._capsule_expanded:
            if not self._panel.isVisible():
                self._capsule_expanded = False
                self._animate_capsule(expand=False)
        super().leaveEvent(event)

    def _animate_capsule(self, expand: bool):
        if getattr(self, "_expand_anim", None) is not None:
            self._expand_anim.stop()
            self._expand_anim.deleteLater()
            self._expand_anim = None

        dpr = win32_utils.get_system_dpi() / 96
        start_w = self.width()

        if expand:
            self._bar.set_capsule_collapsed(False)
            end_w = self._bar.desired_width()
        else:
            end_w = int(128 * dpr)

        if abs(start_w - end_w) < 4:
            if not expand:
                self._bar.set_capsule_collapsed(True)
            self.reposition(force=True)
            return

        self._expand_anim = QVariantAnimation(self)
        self._expand_anim.setDuration(220)
        self._expand_anim.setStartValue(start_w)
        self._expand_anim.setEndValue(end_w)
        self._expand_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        right_phys = self.x() + self.width()

        def _step(val):
            w = int(val)
            x = right_phys - w
            self.setGeometry(x, self.y(), w, self.height())
            self._bar._swp_frame(time.monotonic())

        def _finished():
            if getattr(self, "_expand_anim", None) is not None:
                self._expand_anim.deleteLater()
                self._expand_anim = None
            if not expand:
                self._bar.set_capsule_collapsed(True)
            else:
                if not self._menu_open and not self._panel.isVisible():
                    self._panel.popup(self._cfg, self._anchor_rect())
            self.reposition(force=True)

        self._expand_anim.valueChanged.connect(_step)
        self._expand_anim.finished.connect(_finished)
        self._expand_anim.start()

    def apply_panel_font(self):
        style = self._cfg.get("style", {})
        font = QFont(style.get("fontFamily", "Microsoft YaHei UI"))
        font.setPixelSize(12)
        self._panel.set_panel_font(font)