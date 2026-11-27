"""app.platform — Windows 平台互操作层（Win32 / DWM / UIA / 注册表自启）。"""

from . import autostart, glass, win32_utils

__all__ = ["autostart", "glass", "win32_utils"]
