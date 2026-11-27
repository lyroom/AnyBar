import ctypes
import os
import sys

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

from ctypes import wintypes

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.platform import win32_utils
from app.core import config as config_mod
from app.gui.taskbar.window import TaskbarWindow


def main():
    win32_utils.enable_dpi_awareness()
    app = QApplication(sys.argv)
    cfg = config_mod.load_config()
    win = TaskbarWindow(cfg)
    results = {}

    def check():
        try:
            hwnd = int(win.winId())
            results["hwnd"] = hwnd
            results["parent"] = win32_utils.user32.GetParent(hwnd)
            ph = results["parent"]
            if ph:
                pbuf = ctypes.create_unicode_buffer(256)
                win32_utils.user32.GetClassNameW(ph, pbuf, 256)
                results["parent_cls"] = pbuf.value
            results["rect"] = win32_utils.get_rect(hwnd)
            results["taskbar"] = win32_utils.find_taskbar()
            results["tray_left"] = win32_utils.tray_notify_left_in_taskbar()
            r = results["rect"]
            if r:
                pt = wintypes.POINT((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
                hit = win32_utils.user32.WindowFromPoint(pt)
                buf = ctypes.create_unicode_buffer(256)
                win32_utils.user32.GetClassNameW(hit, buf, 256)
                results["hit_class"] = buf.value
            taskbar = results["taskbar"]
            if taskbar:
                order = []
                h = None
                while True:
                    h = win32_utils.user32.FindWindowExW(taskbar, h, None, None)
                    if not h:
                        break
                    order.append(h)
                results["zorder_rank"] = order.index(hwnd) if hwnd in order else -1
                results["zorder"] = [win32_utils.class_name_safe(x) if hasattr(win32_utils, "class_name_safe") else x for x in order[:4]]
        except Exception as e:
            results["error"] = repr(e)
        QTimer.singleShot(1000, app.quit)

    QTimer.singleShot(2500, check)
    app.exec()
    print("self-test:", results)
    r = results.get("rect")
    taskbar = results.get("taskbar")
    tb_rect = win32_utils.get_rect(taskbar) if taskbar else None
    tray = win32_utils.find_tray_notify(taskbar) if taskbar else None
    tray_rect = win32_utils.get_rect(tray) if tray else None
    tray_left = tray_rect[0] if tray_rect else None
    parent_cls = results.get("parent_cls", "")
    ok = (parent_cls == "AnyBarHostWnd"
          and taskbar
          and r is not None
          and tb_rect is not None
          and tray_left is not None
          and r[1] >= tb_rect[1] and r[3] <= tb_rect[3]
          and r[2] <= tray_left)

    print("EMBED:", "OK" if ok else "FAIL", "| parent_cls:", parent_cls,
          "| tray_left:", tray_left, "| bar:", r,
          "| in_taskbar:", (r[1] >= tb_rect[1] and r[3] <= tb_rect[3]) if r and tb_rect else None,
          "| bar_right<=tray_left:", (r[2] <= tray_left) if (r and tray_left is not None) else None)


if __name__ == "__main__":
    main()