"""app/sources/__init__.py — 数据源定义与集中注册表（纯逻辑无 Qt 依赖）

任何数据源（算力额度、系统信息、天气、股票等）通过 @register(SourceInfo(...))
向本模块登记，供调度层 (SourceService) 与表现层 (Bar/Panel/Settings) 消费。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import os
from pathlib import Path
from typing import Any, Callable

from app.core.logger import get_logger

_logger = get_logger("anybar.sources", "sources.log")


@dataclass
class SourceInfo:
    id: str                                  # 唯一标识，如 "quota", "system", "weather", "stock"
    title: str                                # 设置页显示名
    description: str = ""                     # 扩展插件卡片副标题/详细描述
    kind: str = "remote"                      # "local" | "remote"（本地秒级无网络 vs 远程网络 IO）
    default_interval_sec: int = 60            # 默认轮询间隔（秒）
    min_interval_sec: int = 1                 # 允许配置的最小间隔（秒）
    needs_credentials: bool = False           # 是否需要凭据配置
    config_schema: dict[str, Any] = field(default_factory=dict)  # 声明式配置项
    # 可选：启动时读取上次落盘的结果 (cfg) -> (tiles, ts) | None，使远程源无需等网络即可出图
    cache_loader: Callable[[dict[str, Any]], Any] | None = None


@dataclass
class SourceRegistration:
    info: SourceInfo
    fetch_fn: Callable[..., list[dict[str, Any]]]


SOURCES: dict[str, SourceRegistration] = {}


def register(info: SourceInfo) -> Callable[[Callable[..., list[dict[str, Any]]]], Callable[..., list[dict[str, Any]]]]:
    """数据源注册装饰器：将模块的 fetch 函数与元数据注册进 SOURCES。"""
    def _decorator(fn: Callable[..., list[dict[str, Any]]]) -> Callable[..., list[dict[str, Any]]]:
        SOURCES[info.id] = SourceRegistration(info=info, fetch_fn=fn)
        return fn
    return _decorator


def get_source(source_id: str) -> SourceRegistration | None:
    return SOURCES.get(source_id)


def list_sources() -> list[SourceRegistration]:
    return list(SOURCES.values())


def unregister(source_id: str) -> None:
    """仅供测试或动态卸载使用。"""
    SOURCES.pop(source_id, None)


def get_user_plugins_dir() -> Path:
    """获取用户自定义插件目录：%APPDATA%/AnyBar/plugins/（若无 APPDATA 则降级为 ~/.anybar/plugins/）。"""
    appdata = os.environ.get("APPDATA")
    if appdata:
        p = Path(appdata) / "AnyBar" / "plugins"
    else:
        p = Path.home() / ".anybar" / "plugins"
    return p


def load_user_plugins(plugins_dir: Path | None = None) -> list[str]:
    """扫描并动态加载用户本地插件目录中的 *.py 文件。

    用户可在该目录下编写任意自定义数据源插件，使用 @register(SourceInfo(...)) 自动挂载。
    """
    if plugins_dir is None:
        plugins_dir = get_user_plugins_dir()

    loaded = []
    try:
        plugins_dir.mkdir(parents=True, exist_ok=True)
        # 若无示例文件，写入示例参考文件（带 .sample 后缀，避免默认直接被当作插件加载）
        sample_file = plugins_dir / "example_source.py.sample"
        if not sample_file.exists():
            sample_file.write_text(
                    '"""AnyBar 用户自制插件示例\n'
                    '将后缀改为 .py 并重启 AnyBar，即可在设置与常驻条中生效。\n'
                    '"""\n'
                    'from app.sources import SourceInfo, register\n'
                    'from app.tiles import make_tile\n\n'
                    '@register(\n'
                    '    SourceInfo(\n'
                    '        id="demo_user_metric",\n'
                    '        title="自定义演示指标",\n'
                    '        description="用户本地插件演示",\n'
                    '        kind="local",\n'
                    '        default_interval_sec=5,\n'
                    '    )\n'
                    ')\n'
                    'def fetch_demo_metric(cfg: dict, timeout: float = 2.0) -> list[dict]:\n'
                    '    return [\n'
                    '        make_tile(\n'
                    '            id="demo:status",\n'
                    '            source="demo_user_metric",\n'
                    '            name="Plugin",\n'
                    '            ratio=0.85,\n'
                    '            center_text="85%",\n'
                    '            sub_text="运行正常",\n'
                    '            color="#10B981",\n'
                    '            kind="ring",\n'
                    '        )\n'
                    '    ]\n',
                    encoding="utf-8",
                )
    except OSError as err:
        _logger.warning("创建用户插件目录失败: %s", err)
        return []

    for py_file in plugins_dir.glob("*.py"):
        if py_file.name.startswith(("_", ".")):
            continue
        mod_name = f"anybar_user_plugin_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, str(py_file))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                loaded.append(py_file.stem)
                _logger.info("已成功挂载用户插件: %s", py_file.name)
        except Exception as err:
            _logger.warning("加载用户插件 %s 出错: %s", py_file.name, err)

    return loaded


def _load_builtin_sources() -> None:
    from . import (  # noqa: F401
        claude_source,
        cursor_source,
        deepseek_source,
        dev_source,
        quota_source,
        system_source,
        weather_source,
    )
    load_user_plugins()


_load_builtin_sources()
