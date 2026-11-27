"""app/styles/qss_engine.py — 独立 QSS 模板编译引擎与动态属性驱动辅助

将样式声明从 Python 组件代码中彻底抽离：
1. 从 app/styles/qss/*.qss（开发态或 PyInstaller _MEIPASS 冻结态）加载纯选择器 QSS 模板；
2. 基于 ThemeTokens 与 screen_scale 编译 {{token}} 及 {{px:12.5}} 占位符并缓存编译结果；
3. 提供 set_role / set_prop / set_transparent / repolish 原语，组件只需声明语义属性，
   由顶层容器挂载的样式表统一着色，消除散落在业务组件中的内联 setStyleSheet 调用。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from . import tokens

_TOKEN_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
_PX_RE = re.compile(r"\{\{\s*px:([0-9]+(?:\.[0-9]+)?)\s*\}\}")

_RAW_TEMPLATE_CACHE: dict[str, str] = {}
_COMPILED_CACHE: dict[tuple[Any, ...], str] = {}


def qss_dir() -> Path:
    """定位独立 QSS 样式表目录，同时兼容源码运行与 PyInstaller 单文件 EXE。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        frozen_dir = Path(str(meipass)) / "app" / "styles" / "qss"
        if frozen_dir.is_dir():
            return frozen_dir
    return Path(__file__).resolve().parent / "qss"


def load_template(name: str) -> str:
    """加载指定名称（可带或不带 .qss 后缀）的原始 QSS 模板并缓存。"""
    fname = name if name.endswith(".qss") else f"{name}.qss"
    cached = _RAW_TEMPLATE_CACHE.get(fname)
    if cached is not None:
        return cached
    path = qss_dir() / fname
    content = path.read_text(encoding="utf-8")
    _RAW_TEMPLATE_CACHE[fname] = content
    return content


def list_qss_templates() -> list[str]:
    """列出 app/styles/qss/ 下全部独立 QSS 模板名（不含后缀）。"""
    d = qss_dir()
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.qss"))


def clear_cache() -> None:
    """清空模板与编译缓存（供热重载或测试调用）。"""
    _RAW_TEMPLATE_CACHE.clear()
    _COMPILED_CACHE.clear()


def _build_context(dark: bool, scale: float, extra: dict[str, Any] | None = None) -> dict[str, str]:
    t = tokens.get_tokens(dark)
    ctx: dict[str, str] = {}
    for k, v in t.as_dict().items():
        if isinstance(v, (str, int, float)):
            ctx[k] = str(v)
    # 常用派生尺寸令牌
    ctx["radius_panel"] = str(tokens.spx(tokens.RADIUS["panel"], scale))
    ctx["radius_card"] = str(tokens.spx(tokens.RADIUS["card"], scale))
    ctx["radius_row_card"] = str(tokens.spx(tokens.RADIUS["card"] - 2, scale))
    ctx["radius_inner"] = str(tokens.spx(tokens.RADIUS["inner"], scale))
    ctx["radius_control"] = str(tokens.spx(tokens.RADIUS["control"], scale))
    ctx["radius_add_btn"] = str(tokens.spx(tokens.RADIUS["control"] + 2, scale))
    ctx["radius_badge"] = str(tokens.spx(tokens.RADIUS["badge"], scale))
    ctx["weather_city_bg"] = "rgba(255,255,255,22)" if dark else "rgba(255,255,255,220)"
    ctx["weather_city_border"] = "rgba(255,255,255,44)" if dark else t.border
    if extra:
        for k, v in extra.items():
            ctx[str(k)] = str(v)
    return ctx


def compile_template_text(
    template: str,
    dark: bool,
    scale: float = 1.0,
    extra: dict[str, Any] | None = None,
) -> str:
    """将 QSS 模板文本中的 {{px:N}} 与 {{token}} 占位符编译为最终可执行 QSS。"""
    s = max(0.5, float(scale))
    ctx = _build_context(dark, s, extra)

    def _repl_px(m: re.Match[str]) -> str:
        val = float(m.group(1))
        return str(tokens.spx(val, s))

    def _repl_tok(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in ctx:
            raise KeyError(f"QSS 模板引用了未定义变量: {{{{{key}}}}}")
        return ctx[key]

    out = _PX_RE.sub(_repl_px, template)
    out = _TOKEN_RE.sub(_repl_tok, out)
    return out


def compile_qss(
    name: str,
    dark: bool,
    scale: float = 1.0,
    extra: dict[str, Any] | None = None,
) -> str:
    """编译单个独立 .qss 模板文件并按参数元组缓存结果。"""
    extra_key = tuple(sorted((str(k), str(v)) for k, v in (extra or {}).items()))
    cache_key = (name, bool(dark), round(float(scale), 3), extra_key)
    cached = _COMPILED_CACHE.get(cache_key)
    if cached is not None:
        return cached
    raw = load_template(name)
    compiled = compile_template_text(raw, dark=dark, scale=scale, extra=extra)
    _COMPILED_CACHE[cache_key] = compiled
    return compiled


def compile_bundle(
    names: tuple[str, ...] | list[str],
    dark: bool,
    scale: float = 1.0,
    extra: dict[str, Any] | None = None,
) -> str:
    """按顺序拼接并编译多个独立 .qss 文件为单一完整样式表。"""
    parts = [compile_qss(n, dark=dark, scale=scale, extra=extra) for n in names]
    return "\n".join(parts)


# ── Qt 动态属性驱动辅助（消除组件侧散落的内联 setStyleSheet） ─────────────────

def repolish(widget) -> None:
    """触发 Qt 样式系统重新匹配动态属性选择器（如 [role="muted"] / [active="true"]）。"""
    if widget is None:
        return
    st = widget.style()
    if st is not None:
        st.unpolish(widget)
        st.polish(widget)
    widget.update()


def set_prop(widget, name: str, value: Any, *, polish: bool = True):
    """设置控件 Qt 动态属性并按需触发样式重算，返回控件本身便于链式使用。"""
    if widget is None:
        return widget
    if widget.property(name) != value:
        widget.setProperty(name, value)
        if polish:
            repolish(widget)
    return widget


def set_role(widget, role: str, *, polish: bool = True):
    """设置语义角色属性（primary / secondary / muted / accent / ok / warn / danger / info / violet / divider）。"""
    return set_prop(widget, "role", role, polish=polish)


def set_transparent(widget, enabled: bool = True, *, polish: bool = False):
    """将布局容器标记为透明无边框（由 common.qss 的 QWidget[transparent="true"] 规则匹配）。"""
    return set_prop(widget, "transparent", "true" if enabled else "false", polish=polish)
