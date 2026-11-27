"""app/tokens.py — AnyBar 统一设计令牌（Design Tokens，单一真相源，无 Qt 依赖）

Liquid Fluent 视觉体系：
- 深色模式（Neutral Obsidian 微冷石墨）：#121418 -> #1A1D24 -> #222630
- 浅色模式（Cloud Mica 温润云母白）：#F3F5F8 -> #FFFFFF -> #F7F9FC
- 严格同心圆角阶梯：外框 16 -> 卡片 12 -> 控件/子块 8 -> 徽章 6
- 统一排版字阶与物理动效时序常量
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# 字体家族栈
FONT_UI = ("Segoe UI Variable Display", "Microsoft YaHei UI", "Segoe UI", "Microsoft YaHei")
FONT_TEXT = ("Microsoft YaHei UI", "Segoe UI Variable Text", "Segoe UI")
FONT_MONO = ("Cascadia Mono", "Consolas", "Segoe UI")

# 严格同心圆角阶梯（逻辑像素，渲染时乘以 screen_scale）
RADIUS = {
    "panel": 16,
    "card": 12,
    "inner": 8,
    "control": 8,
    "badge": 6,
    "pill": 999,
}

# 间距阶梯（逻辑像素）
SPACE = {
    "xxs": 2,
    "xs": 4,
    "sm": 6,
    "md": 10,
    "lg": 14,
    "xl": 18,
}

# 排版字阶（逻辑像素）
TYPE = {
    "display": 28.0,
    "title": 14.5,
    "section": 13.0,
    "body": 12.5,
    "caption": 11.0,
    "micro": 10.0,
}

# 物理动效时序（毫秒）
MOTION = {
    "micro": 130,       # hover 变色 / 按压反馈
    "fast": 160,        # 轻过渡 / 切页
    "standard": 200,    # 滑块滑动 / 视图切换 / 抽屉展开
    "emphasis": 260,    # 数值圆环插值 / 进度条阻尼 / 复选弹跳
    "panel_in": 190,    # 浮窗滑入
    "panel_out": 125,   # 浮窗淡出
    "toast_hold": 2400, # Toast 停留时长
}


def spx(value: float, scale: float, lo: int = 1) -> int:
    """将逻辑像素按 DPI 缩放因子换算为物理整数像素。"""
    return max(lo, int(round(float(value) * float(scale))))


@dataclass(frozen=True)
class ThemeTokens:
    dark: bool

    # 表面阶梯（Elevation）
    canvas: str
    canvas_top: str
    canvas_border: str
    canvas_border_hex: str
    surface: str
    surface_top: str
    surface_elevated: str
    surface_hover: str
    surface_press: str
    surface_sunken: str

    # 边线与分割线
    border: str
    border_subtle: str
    border_strong: str
    divider: str
    divider_rgba: tuple[int, int, int, int]

    # 光学高光与环境阴影（RGBA 元组，供 QPainter 使用）
    rim_top: tuple[int, int, int, int]
    rim_mid: tuple[int, int, int, int]
    rim_bottom: tuple[int, int, int, int]
    shadow_ambient: tuple[int, int, int, int]

    # 文字阶梯
    text: str
    text_secondary: str
    text_muted: str
    text_disabled: str
    text_on_accent: str

    # 主强调色
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str
    accent_soft_hover: str
    accent_border: str

    # 语义状态色
    ok: str
    ok_solid: str
    ok_soft: str
    warn: str
    warn_solid: str
    warn_soft: str
    danger: str
    danger_solid: str
    danger_soft: str
    danger_border: str
    info: str
    info_soft: str
    violet: str
    violet_soft: str

    # 进度条 / 圆环底轨
    track: str
    track_alpha: tuple[int, int, int, int]

    # 常驻条液态玻璃（常态 alpha 远大于 28 鼠标命中门槛）
    glass_top: tuple[int, int, int, int]
    glass_bottom: tuple[int, int, int, int]
    glass_rim_top: tuple[int, int, int, int]
    glass_rim_bottom: tuple[int, int, int, int]

    # 菜单与图标
    menu_bg: str
    menu_border: str
    menu_sel: str
    icon: str
    icon_muted: str

    # Win11 DWM 标题栏 COLORREF（0x00BBGGRR）
    titlebar_bgr: int

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


DARK_TOKENS = ThemeTokens(
    dark=True,

    canvas="#121418",
    canvas_top="#171B22",
    canvas_border="rgba(255,255,255,26)",
    canvas_border_hex="#262B35",
    surface="#1A1D24",
    surface_top="#20242D",
    surface_elevated="#222630",
    surface_hover="#282D3A",
    surface_press="#303645",
    surface_sunken="#101216",

    border="#2B303C",
    border_subtle="rgba(255,255,255,16)",
    border_strong="#3C4354",
    divider="rgba(255,255,255,15)",
    divider_rgba=(255, 255, 255, 18),

    rim_top=(255, 255, 255, 48),
    rim_mid=(255, 255, 255, 14),
    rim_bottom=(255, 255, 255, 4),
    shadow_ambient=(0, 0, 0, 44),

    text="#F3F5F8",
    text_secondary="#B6BFCC",
    text_muted="#7E8798",
    text_disabled="#505867",
    text_on_accent="#FFFFFF",

    accent="#5CA4FF",
    accent_hover="#7BB6FF",
    accent_pressed="#3F8FF6",
    accent_soft="rgba(92,164,255,28)",
    accent_soft_hover="rgba(92,164,255,46)",
    accent_border="rgba(92,164,255,95)",

    ok="#34D399",
    ok_solid="#10B981",
    ok_soft="rgba(52,211,153,28)",
    warn="#FBBF24",
    warn_solid="#F59E0B",
    warn_soft="rgba(251,191,36,28)",
    danger="#F87171",
    danger_solid="#EF4444",
    danger_soft="rgba(248,113,113,28)",
    danger_border="rgba(248,113,113,78)",
    info="#38BDF8",
    info_soft="rgba(56,189,248,28)",
    violet="#A78BFA",
    violet_soft="rgba(167,139,250,28)",

    track="#2A2F3C",
    track_alpha=(255, 255, 255, 28),

    glass_top=(38, 43, 54, 192),
    glass_bottom=(22, 25, 32, 166),
    glass_rim_top=(255, 255, 255, 82),
    glass_rim_bottom=(255, 255, 255, 18),

    menu_bg="#1B1F27",
    menu_border="#2E3442",
    menu_sel="rgba(92,164,255,44)",
    icon="#C9D1DD",
    icon_muted="#7E8798",

    titlebar_bgr=0x00181412,
)


LIGHT_TOKENS = ThemeTokens(
    dark=False,

    canvas="#F3F5F8",
    canvas_top="#F8FAFD",
    canvas_border="rgba(15,23,42,24)",
    canvas_border_hex="#D5DCE6",
    surface="#FFFFFF",
    surface_top="#FFFFFF",
    surface_elevated="#F7F9FC",
    surface_hover="#EEF2F7",
    surface_press="#E3E9F2",
    surface_sunken="#EAEFF5",

    border="#E1E6EF",
    border_subtle="rgba(15,23,42,14)",
    border_strong="#C3CCD9",
    divider="rgba(15,23,42,13)",
    divider_rgba=(15, 23, 42, 16),

    rim_top=(255, 255, 255, 245),
    rim_mid=(255, 255, 255, 130),
    rim_bottom=(203, 213, 225, 65),
    shadow_ambient=(15, 23, 42, 16),

    text="#11151C",
    text_secondary="#4A5464",
    text_muted="#788294",
    text_disabled="#A7B0BF",
    text_on_accent="#FFFFFF",

    accent="#2563EB",
    accent_hover="#1D4ED8",
    accent_pressed="#1E40AF",
    accent_soft="rgba(37,99,235,20)",
    accent_soft_hover="rgba(37,99,235,34)",
    accent_border="rgba(37,99,235,90)",

    ok="#059669",
    ok_solid="#10B981",
    ok_soft="rgba(16,185,129,24)",
    warn="#D97706",
    warn_solid="#F59E0B",
    warn_soft="rgba(245,158,11,26)",
    danger="#DC2626",
    danger_solid="#EF4444",
    danger_soft="rgba(239,68,68,22)",
    danger_border="rgba(239,68,68,65)",
    info="#0284C7",
    info_soft="rgba(2,132,199,22)",
    violet="#7C3AED",
    violet_soft="rgba(124,58,237,22)",

    track="#E1E6EF",
    track_alpha=(15, 23, 42, 22),

    glass_top=(255, 255, 255, 186),
    glass_bottom=(244, 247, 252, 142),
    glass_rim_top=(255, 255, 255, 240),
    glass_rim_bottom=(148, 163, 184, 96),

    menu_bg="#FCFDFE",
    menu_border="#D5DCE6",
    menu_sel="rgba(37,99,235,24)",
    icon="#3B4352",
    icon_muted="#788294",

    titlebar_bgr=0x00F8F5F3,
)


def get_tokens(dark: bool) -> ThemeTokens:
    """获取当前主题模式对应的唯一设计令牌对象。"""
    return DARK_TOKENS if dark else LIGHT_TOKENS


def quota_tier_colors(ratio: float, dark: bool) -> tuple[str, str]:
    """根据剩余比例 (0.0~1.0) 返回统一的 (进度条主色, 数值文字色)。"""
    t = get_tokens(dark)
    if ratio <= 0.20:
        return t.danger_solid, t.danger
    if ratio <= 0.50:
        return t.warn_solid, t.warn
    return t.ok_solid, t.ok


def load_tier_color(ratio: float, dark: bool) -> str:
    """根据负载率 (0.0~1.0，如 CPU/RAM/Disk) 返回语义状态色。"""
    t = get_tokens(dark)
    if ratio > 0.88:
        return t.danger_solid
    if ratio > 0.75:
        return t.warn_solid
    return t.accent
