import ctypes
import ctypes.wintypes
import os
import signal
import sys

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog

from app.platform import autostart
from app.styles import theme
from app.platform import win32_utils
from app.core import config as config_mod
from app.gui.taskbar.window import TaskbarWindow
from app.core.logger import install_qt_message_filter
from app.gui.settings import SettingsDialog

MUTEX_NAME = "Local\\AnyBarMutex"
ERROR_ALREADY_EXISTS = 183

_mutex_handle = None


def acquire_single_instance() -> bool:
    global _mutex_handle
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    err = ctypes.get_last_error()
    if not _mutex_handle:
        return False
    return err != ERROR_ALREADY_EXISTS


def _resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel)


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    win32_utils.enable_dpi_awareness()
    if not acquire_single_instance():
        print("AnyBar 已在运行中")
        return
    autostart.migrate_legacy_autostart()
    app = QApplication(sys.argv)
    install_qt_message_filter()
    theme.install_qt_zh_cn_translator(app)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("AnyBar")
    icon = QIcon(_resource_path("assets/icon.ico"))
    if not icon.isNull():
        app.setWindowIcon(icon)

    cfg = config_mod.load_config()
    win = TaskbarWindow(cfg)

    def open_settings():
        dlg = SettingsDialog(None, cfg, preview_callback=win.apply_config)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cfg.clear()
            cfg.update(dlg.get_config())
            config_mod.save_config(cfg)
            win.apply_config(cfg)
        dlg.deleteLater()
        import gc
        gc.collect()

    def quit_app():
        app.quit()

    win._bar.request_settings.connect(open_settings)
    win._bar.request_edit_todos.connect(lambda: win._open_edit_todos())
    win._bar.request_quit.connect(quit_app)
    # app.quit() 不走 closeEvent，退出循环后立刻拆嵌入，防 external WM_DESTROY
    app.aboutToQuit.connect(win.shutdown)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()