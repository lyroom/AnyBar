"""AnyBar 应用主包。

分层结构：
- app.core     : 核心领域逻辑、配置持久化、数据源插件与后台调度
- app.platform : Windows 平台底层互操作（Win32 嵌入 / DWM / UIA / 开机自启）
- app.styles   : 设计令牌、独立 QSS 模板引擎、主题与矢量图标
- app.gui      : GUI 表现层（通用控件、任务栏常驻条、悬停浮窗卡片、设置中心）
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys


_PLUGIN_COMPAT_ALIASES: dict[str, str] = {
    "app.sources": "app.core.sources",
    "app.tiles": "app.core.tiles",
}


class _PluginCompatLoader(importlib.abc.Loader):
    """将第三方插件旧导入路径映射到 app.core 同一单例模块对象，防止注册表分裂。"""

    def __init__(self, target_name: str) -> None:
        self._target_name = target_name

    def create_module(self, spec):
        return importlib.import_module(self._target_name)

    def exec_module(self, module) -> None:
        # 目标模块已由 importlib.import_module 执行完毕，确保 sys.modules 指向同一实例
        pass


class _PluginCompatFinder(importlib.abc.MetaPathFinder):
    """仅拦截 app.sources / app.tiles 及其子模块，供用户外部插件零修改兼容。"""

    def find_spec(self, fullname: str, path=None, target=None):
        mapped = _PLUGIN_COMPAT_ALIASES.get(fullname)
        if mapped is None:
            for old_prefix, new_prefix in _PLUGIN_COMPAT_ALIASES.items():
                if fullname.startswith(old_prefix + "."):
                    mapped = new_prefix + fullname[len(old_prefix):]
                    break
        if mapped is None:
            return None
        return importlib.machinery.ModuleSpec(
            fullname,
            _PluginCompatLoader(mapped),
            is_package=(mapped == "app.core.sources"),
        )


def _install_plugin_compat_finder() -> None:
    if not any(isinstance(f, _PluginCompatFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _PluginCompatFinder())


_install_plugin_compat_finder()
