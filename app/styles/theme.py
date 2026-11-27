"""app/styles/theme.py — 基于 tokens 与 qss_engine 的主题管理与样式表外观层

所有样式表均由 app/styles/qss/*.qss 独立模板经 qss_engine 编译而来；
本模块负责系统深浅色监听、主题模式切换、字体工厂、DPI 缩放、矢量对勾/箭头图元缓存与向后兼容接口。
"""

from __future__ import annotations

import os
import sys
import tempfile
import winreg

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QPointF, QTranslator, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPen, QPixmap

from . import qss_engine, tokens

_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
VALID_THEME_MODES = ("auto", "light", "dark")
_THEME_MODE = "auto"


def install_qt_zh_cn_translator(app=None) -> bool:
    """加载 Qt 官方简体中文翻译包（qtbase_zh_CN.qm），汉化颜色选择器、输入框右键菜单等内置控件。"""
    target = app if app is not None else QCoreApplication.instance()
    if target is None:
        return False
    if getattr(target, "_anybar_qt_zh_translator", None) is not None:
        return True

    search_dirs: list[str] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        search_dirs.append(os.path.join(str(meipass), "translations"))
    try:
        qt_tr_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if qt_tr_dir:
            search_dirs.append(str(qt_tr_dir))
    except Exception:
        pass
    try:
        import PySide6
        pkg_tr = os.path.join(os.path.dirname(PySide6.__file__), "translations")
        if pkg_tr not in search_dirs:
            search_dirs.append(pkg_tr)
    except Exception:
        pass

    tr = QTranslator(target)
    for d in search_dirs:
        if d and os.path.isdir(d) and tr.load("qtbase_zh_CN", d):
            target.installTranslator(tr)
            setattr(target, "_anybar_qt_zh_translator", tr)
            return True
    return False


def set_theme_mode(mode: str | None) -> str:
    """设置全局界面主题模式：'auto'（跟随系统）/ 'light'（浅色）/ 'dark'（深色）。"""
    global _THEME_MODE
    val = str(mode or "auto").strip().lower()
    _THEME_MODE = val if val in VALID_THEME_MODES else "auto"
    return _THEME_MODE


def get_theme_mode() -> str:
    """获取当前生效的界面主题模式设置。"""
    return _THEME_MODE


def apply_theme_mode_from_cfg(cfg: dict | None) -> str:
    """从配置字典同步全局主题模式。"""
    style = (cfg or {}).get("style") if isinstance(cfg, dict) else None
    mode = style.get("themeMode", "auto") if isinstance(style, dict) else "auto"
    return set_theme_mode(mode)


def _spx(value: float, scale: float, lo: int = 1) -> int:
    return tokens.spx(value, scale, lo=lo)


def screen_scale(screen=None) -> float:
    try:
        if screen is None:
            screen = (QGuiApplication.screenAt(QCursor.pos())
                      or QGuiApplication.primaryScreen())
        if screen is not None:
            dpi = float(screen.logicalDotsPerInch())
            if dpi > 0:
                return max(1.0, dpi / 96.0)
    except (RuntimeError, AttributeError):
        pass
    try:
        from app.platform import win32_utils
        return max(1.0, win32_utils.get_system_dpi() / 96.0)
    except Exception:
        return 1.0


def ui_font(px: float, weight: int = 400, mono: bool = False) -> QFont:
    """统一排版字体构造器。"""
    f = QFont()
    f.setFamilies(list(tokens.FONT_MONO if mono else tokens.FONT_UI))
    f.setPixelSize(max(9, int(round(px))))
    f.setWeight(QFont.Weight(weight))
    return f


def get_tokens(dark: bool) -> tokens.ThemeTokens:
    return tokens.get_tokens(dark)


CHECK_GREEN = tokens.LIGHT_TOKENS.ok_solid
CHECK_ACCENT = tokens.LIGHT_TOKENS.accent
CHECK_ACCENT_HOVER = tokens.LIGHT_TOKENS.accent_hover


def check_icon_path(size: int = 16) -> str:
    size = max(12, int(round(size)))
    path = os.path.join(tempfile.gettempdir(), "anybar", f"check_v4_{size}.png")
    if os.path.exists(path):
        return path
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#FFFFFF"), max(1.6, size * 0.105))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    s = float(size)
    p.drawPolyline([
        QPointF(s * 0.25, s * 0.52),
        QPointF(s * 0.44, s * 0.70),
        QPointF(s * 0.76, s * 0.32),
    ])
    p.end()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pm.save(path, "PNG")
    except OSError:
        pass
    return path


def _reg_is_dark() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE) as key:
            value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
            return value == 0
    except OSError:
        return True


def is_system_dark() -> bool:
    if _THEME_MODE == "dark":
        return True
    if _THEME_MODE == "light":
        return False
    try:
        hints = QGuiApplication.styleHints()
        scheme = hints.colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
    except (RuntimeError, AttributeError):
        pass
    return _reg_is_dark()


def auto_text_color(cfg_style: dict) -> str:
    dark = is_system_dark()
    t = tokens.get_tokens(dark)
    if cfg_style.get("autoColor", True):
        return t.text
    if dark:
        return cfg_style.get("darkThemeColor", t.text)
    return cfg_style.get("lightThemeColor", t.text)


# ── 向后兼容调色板适配器（全部由统一 tokens 派生） ─────────────────────────

def semantic_palette(dark: bool) -> dict:
    t = tokens.get_tokens(dark)
    return {
        "main": t.text,
        "schedule_active": t.warn,
        "todo": t.info,
        "note": t.text_muted,
        "dim": t.text_muted,
        "panel_bg": t.canvas,
    }


def fluent_palette(dark: bool) -> dict:
    t = tokens.get_tokens(dark)
    return {
        "accent": t.accent,
        "accent_hover": t.accent_hover,
        "accent_solid_hover": t.accent_pressed,
        "accent_focus_bg": t.accent_soft,
        "amber": t.warn,
        "danger": t.danger,
        "ok": t.ok,
        "window_bg": t.canvas,
        "text": t.text,
        "text_dim": t.text_muted,
        "todo_done": t.text_muted,
        "card_bg": t.surface,
        "card_border": t.border,
        "card_hover": t.surface_hover,
        "row_hover": t.surface_hover,
        "input_bg": t.surface_sunken,
        "input_border": t.border_strong,
        "control_bg": t.surface_elevated,
        "control_hover": t.surface_hover,
        "control_press": t.surface_press,
        "sep": t.divider,
        "menu_bg": t.menu_bg,
        "menu_sel": t.menu_sel,
        "menu_border": t.menu_border,
        "icon": t.icon,
    }


def hig_palette(dark: bool) -> dict:
    t = tokens.get_tokens(dark)
    return {
        "seg_slot": t.surface_sunken,
        "seg_active": t.surface_elevated if dark else t.surface,
        "seg_active_border": t.border_strong,
        "seg_active_text": t.text,
        "seg_text": t.text_muted,
        "bar_row1": t.text,
        "bar_row2": t.text_secondary,
        "dot_amber": t.warn_solid,
        "dot_green": t.ok_solid,
        "spec_top": t.warn,
        "spec_bottom": t.warn_solid,
        "tip": t.text_muted,
        "now_bar": t.warn_solid,
        "now_track": t.track,
        "quota_green": t.ok_solid,
        "quota_blue": t.accent,
        "quota_red": t.danger_solid,
        "quota_amber": t.warn_solid,
        "time_pill_bg": t.surface_elevated,
        "time_pill_text": t.text_muted,
    }


def bento_palette(dark: bool) -> dict:
    t = tokens.get_tokens(dark)
    return {
        "panel_bg": t.canvas,
        "card_bg": t.surface,
        "card_border": t.border,
        "text": t.text,
        "text_dim": t.text_muted,
        "track": t.track,
        "now_bar": t.warn_solid,
        "quota_blue": t.accent,
        "quota_green": t.ok_solid,
        "quota_red": t.danger_solid,
        "quota_amber": t.warn_solid,
    }


# ── 下拉箭头图元缓存 ────────────────────────────────────────────────────────

_combo_arrow_cache: dict[tuple[bool, float], tuple[str, int, int]] = {}


def combo_arrow_url(dark: bool, scale: float | None = None) -> tuple[str, int, int]:
    if scale is None:
        scale = screen_scale()
    key = (bool(dark), round(float(scale), 3))
    if key in _combo_arrow_cache:
        return _combo_arrow_cache[key]
    t = tokens.get_tokens(dark)
    w = max(12, int(round(12 * scale)))
    h = max(8, int(round(8 * scale)))
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(t.text_muted), max(1.8, 1.65 * scale))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPolyline([
        QPointF(w * 0.22, h * 0.30),
        QPointF(w * 0.50, h * 0.68),
        QPointF(w * 0.78, h * 0.30),
    ])
    p.end()
    d = os.path.join(tempfile.gettempdir(), "anybar")
    url = ""
    try:
        os.makedirs(d, exist_ok=True)
        tag = f"v4_{'dark' if dark else 'light'}_{w}x{h}"
        path = os.path.join(d, f"combo_arrow_{tag}.png")
        if pm.save(path, "PNG"):
            url = path.replace("\\", "/")
    except OSError:
        url = ""
    result = (url, w, h)
    _combo_arrow_cache[key] = result
    return result


def _arrow_image_clause(dark: bool, scale: float = 1.0) -> str:
    url, w, h = combo_arrow_url(dark, scale)
    if url:
        return f"image: url({url}); width: {w}px; height: {h}px;"
    return "width: 0px; height: 0px;"


# ── 基于独立 .qss 模板文件的样式表编译入口 ────────────────────────────────────

def check_indicator_qss(ind_size: int = 16, dark: bool = False,
                        font_px: int | None = None, radius: int | None = None,
                        border: str | None = None, hover: str | None = None,
                        bg: str | None = None) -> str:
    t = tokens.get_tokens(dark)
    ind = max(16, int(round(ind_size)))
    img = check_icon_path(int(round(ind * 0.92))).replace("\\", "/")
    border_c = border or t.border_strong
    bg_c = bg or t.surface_sunken
    hover_c = hover or t.accent
    font_clause = f" font-size: {int(font_px)}px;" if font_px else ""
    corner = int(radius) if radius else max(4, int(round(ind * 0.30)))
    return (
        "QCheckBox {"
        " spacing: 8px;"
        " font-weight: 400;"
        f" color: {t.text};"
        f"{font_clause}"
        " background: transparent;"
        " }"
        "QCheckBox::indicator {"
        f" width: {ind}px; height: {ind}px;"
        f" border-radius: {corner}px;"
        f" border: 1.5px solid {border_c};"
        f" background-color: {bg_c};"
        " }"
        "QCheckBox::indicator:hover {"
        f" border: 1.5px solid {hover_c};"
        f" background-color: {t.accent_soft};"
        " }"
        "QCheckBox::indicator:checked {"
        f" background-color: {t.accent};"
        f" border: 1.5px solid {t.accent};"
        f" image: url({img});"
        " }"
        "QCheckBox::indicator:checked:hover {"
        f" background-color: {t.accent_hover};"
        f" border: 1.5px solid {t.accent_hover};"
        " }"
    )


def menu_qss(dark: bool, scale: float | None = None, compact: bool = False) -> str:
    if scale is None:
        scale = screen_scale()
    return qss_engine.compile_qss(
        "menu",
        dark=dark,
        scale=scale,
        extra={
            "min_w_px": 0 if compact else _spx(168, scale),
            "pad_right": _spx(8 if compact else 22, scale),
        },
    )


def hover_panel_qss(dark: bool, scale: float = 1.0) -> str:
    """悬停浮窗顶层统一样式表（合并 common.qss + hover_panel.qss）。"""
    t = tokens.get_tokens(dark)
    return qss_engine.compile_bundle(
        ("common", "hover_panel"),
        dark=dark,
        scale=scale,
        extra={
            "weather_city_bg": "rgba(255,255,255,22)" if dark else "rgba(255,255,255,220)",
            "weather_city_border": "rgba(255,255,255,44)" if dark else t.border,
        },
    )


def settings_qss(dark: bool, cb_ind_size: int = 18, scale: float = 1.0) -> str:
    """设置中心与向导弹窗共用的统一 Liquid Fluent 样式表（由 common + settings + buttons_inputs 模板编译）。"""
    ind = max(16, int(round(cb_ind_size)))
    img = check_icon_path(int(round(ind * 0.92))).replace("\\", "/")
    corner = max(4, int(round(ind * 0.30)))
    return qss_engine.compile_bundle(
        ("common", "settings", "buttons_inputs"),
        dark=dark,
        scale=scale,
        extra={
            "combo_arrow_clause": _arrow_image_clause(dark, scale),
            "cb_ind": ind,
            "cb_corner": corner,
            "check_img": img,
        },
    )


def dialog_qss(dark: bool, scale: float = 1.0) -> str:
    """子向导弹窗（如 CodingPlanDialog）复用的统一样式表（叠加 dialogs.qss）。"""
    base = settings_qss(dark, _spx(18, scale), scale)
    extra_dlg = qss_engine.compile_qss("dialogs", dark=dark, scale=scale)
    return base + "\n" + extra_dlg


# ── 向后兼容单组件片段生成器（保留供测试与过渡期调用） ─────────────────────────

def row_card_qss(dark: bool, scale: float = 1.0) -> str:
    t = tokens.get_tokens(dark)
    rad = _spx(tokens.RADIUS["card"] - 2, scale)
    return (
        f"QFrame#RowCard {{ background-color: {t.surface};"
        f" border: 1px solid {t.border};"
        f" border-radius: {rad}px; }}"
        f"QFrame#RowCard:hover {{ border-color: {t.border_strong}; }}"
        f'QFrame#RowCard[dragging="true"] {{ background-color: {t.surface_elevated};'
        f" border: 1.5px solid {t.accent}; }}"
    )


def col_header_qss(dark: bool) -> str:
    t = tokens.get_tokens(dark)
    return (
        f"QLabel#colHeader {{ color: {t.text_muted}; border: none;"
        " background: transparent; font-weight: 600; }"
    )


def add_row_qss(dark: bool, scale: float = 1.0) -> str:
    t = tokens.get_tokens(dark)
    rad = _spx(tokens.RADIUS["control"] + 2, scale)
    return (
        "QPushButton#addRowBtn {"
        " background-color: transparent;"
        f" border: 1px dashed {t.border_strong};"
        f" border-radius: {rad}px;"
        f" color: {t.text_secondary};"
        f" padding: 0px {_spx(14, scale)}px;"
        f" font-size: {_spx(12.5, scale)}px;"
        " font-weight: 500;"
        " }"
        "QPushButton#addRowBtn:hover {"
        f" color: {t.accent};"
        f" border-color: {t.accent};"
        f" background-color: {t.accent_soft};"
        " }"
        "QPushButton#addRowBtn:pressed {"
        f" background-color: {t.accent_soft_hover};"
        " }"
    )


def secondary_btn_qss(dark: bool, scale: float = 1.0) -> str:
    t = tokens.get_tokens(dark)
    rad = _spx(tokens.RADIUS["control"], scale)
    return (
        "QPushButton {"
        f" background-color: {t.surface_elevated};"
        f" color: {t.text};"
        f" border: 1px solid {t.border};"
        f" border-radius: {rad}px;"
        f" padding: 0px {_spx(12, scale)}px;"
        f" font-size: {_spx(12, scale)}px;"
        " font-weight: 500;"
        " }"
        "QPushButton:hover {"
        f" background-color: {t.surface_hover};"
        f" border-color: {t.border_strong};"
        " }"
        "QPushButton:pressed {"
        f" background-color: {t.surface_press};"
        " }"
        "QPushButton:disabled {"
        f" color: {t.text_disabled};"
        f" background-color: {t.surface_sunken};"
        " }"
    )


def primary_btn_qss(dark: bool, scale: float = 1.0) -> str:
    t = tokens.get_tokens(dark)
    rad = _spx(tokens.RADIUS["control"], scale)
    return (
        "QPushButton {"
        f" background-color: {t.accent};"
        f" color: {t.text_on_accent};"
        " border: none;"
        f" border-radius: {rad}px;"
        f" padding: 0px {_spx(16, scale)}px;"
        f" font-size: {_spx(12.5, scale)}px;"
        " font-weight: 600;"
        " }"
        f"QPushButton:hover {{ background-color: {t.accent_hover}; }}"
        f"QPushButton:pressed {{ background-color: {t.accent_pressed}; }}"
        f"QPushButton:disabled {{ background-color: {t.surface_hover}; color: {t.text_disabled}; }}"
    )


def input_qss(dark: bool, scale: float = 1.0, radius: float = 8.0) -> str:
    t = tokens.get_tokens(dark)
    r = _spx(radius, scale)
    pad_x = _spx(10, scale)
    return (
        "QLineEdit {"
        f" color: {t.text};"
        f" background-color: {t.surface_sunken};"
        f" border: 1px solid {t.border};"
        f" border-radius: {r}px;"
        f" padding: 0px {pad_x}px;"
        f" selection-background-color: {t.accent};"
        f" selection-color: {t.text_on_accent};"
        " }"
        "QLineEdit:hover {"
        f" border-color: {t.border_strong};"
        " }"
        "QLineEdit:focus {"
        f" background-color: {t.surface};"
        f" border: 1.5px solid {t.accent};"
        " }"
    )
