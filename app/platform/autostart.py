import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "AnyBar"
LEGACY_APP_NAMES = ("FocusBar", "TaskbarReminder")


def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    main_py = Path(__file__).resolve().parent.parent.parent / "main.py"
    return f'"{pythonw}" "{main_py}"'


def migrate_legacy_autostart() -> None:
    """平滑迁移开机启动项：若存在旧版 FocusBar / TaskbarReminder 注册表项，自动迁移为 AnyBar 并清理旧键。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_ALL_ACCESS) as key:
            for legacy_name in LEGACY_APP_NAMES:
                try:
                    old_val, _ = winreg.QueryValueEx(key, legacy_name)
                    try:
                        winreg.QueryValueEx(key, APP_NAME)
                    except FileNotFoundError:
                        new_cmd = _command() if ("main.py" in str(old_val) or getattr(sys, "frozen", False)) else old_val
                        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, new_cmd)
                    try:
                        winreg.DeleteValue(key, legacy_name)
                    except FileNotFoundError:
                        pass
                except FileNotFoundError:
                    pass
    except OSError:
        pass


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            try:
                winreg.QueryValueEx(key, APP_NAME)
                return True
            except FileNotFoundError:
                pass
            for legacy_name in LEGACY_APP_NAMES:
                try:
                    winreg.QueryValueEx(key, legacy_name)
                    return True
                except FileNotFoundError:
                    pass
            return False
    except OSError:
        return False


def enable() -> bool:
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                for legacy_name in LEGACY_APP_NAMES:
                    try:
                        winreg.DeleteValue(key, legacy_name)
                    except OSError:
                        pass
        except OSError:
            pass
        return True
    except OSError:
        return False


def disable() -> bool:
    success = False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, APP_NAME)
                success = True
            except OSError:
                pass
            for legacy_name in LEGACY_APP_NAMES:
                try:
                    winreg.DeleteValue(key, legacy_name)
                    success = True
                except OSError:
                    pass
    except OSError:
        pass
    return success
