import ctypes
from ctypes import wintypes

def _get_titlebar_bgr(dark: bool) -> int:
    from app.styles import tokens
    return tokens.get_tokens(dark).titlebar_bgr

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi


class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint),
                ("AnimationId", ctypes.c_int)]


class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int),
                ("Data", ctypes.POINTER(ACCENT_POLICY)),
                ("SizeOfData", ctypes.c_size_t)]


ACCENT_DISABLED = 0
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
WCA_ACCENT_POLICY = 19
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

user32.SetWindowCompositionAttribute.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA)]
user32.SetWindowCompositionAttribute.restype = wintypes.BOOL
dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long


def apply_acrylic(hwnd, r, g, b, a):
    color = ((a & 0xFF) << 24) | ((b & 0xFF) << 16) | ((g & 0xFF) << 8) | (r & 0xFF)
    policy = ACCENT_POLICY(ACCENT_ENABLE_ACRYLICBLURBEHIND, 2, color, 0)
    data = WINDOWCOMPOSITIONATTRIBDATA(WCA_ACCENT_POLICY, ctypes.pointer(policy), ctypes.sizeof(policy))
    user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))


def disable_acrylic(hwnd):
    policy = ACCENT_POLICY(ACCENT_DISABLED, 0, 0, 0)
    data = WINDOWCOMPOSITIONATTRIBDATA(WCA_ACCENT_POLICY, ctypes.pointer(policy), ctypes.sizeof(policy))
    user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))


def round_corners(hwnd):
    pref = ctypes.c_int(DWMWCP_ROUND)
    dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(pref), 4)


def style_titlebar(hwnd, dark: bool = False):
    """将 Win11 原生标题栏染成与 Liquid Fluent 画布一致的底色（#121418 / #F3F5F8）。"""
    try:
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_CAPTION_COLOR = 35
        dark_val = ctypes.c_int(1 if dark else 0)
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(dark_val), 4)
        color_ref = ctypes.c_uint(_get_titlebar_bgr(dark))
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(color_ref), 4)
    except Exception:
        pass
