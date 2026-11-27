"""tests/test_architecture.py — 分层架构边界、QSS 样式分离、设计模式契约与插件兼容守卫测试。"""

from __future__ import annotations

import ast
import copy
import re
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from app.core import config as config_mod
from app.styles import qss_engine, theme

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = REPO_ROOT / "app"


def _imported_roots(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module)
    return roots


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestLayerBoundaries:
    """验证 Core / Platform / Styles / GUI 四层单向依赖红线与目录整洁度。"""

    def test_app_top_level_contains_only_four_layers(self):
        top_entries = {
            p.name
            for p in APP_ROOT.iterdir()
            if p.name != "__pycache__" and not p.name.startswith(".")
        }
        assert top_entries == {"__init__.py", "core", "platform", "styles", "gui"}

    def test_pure_core_modules_do_not_import_qt(self):
        pure_core = [
            APP_ROOT / "core" / "config.py",
            APP_ROOT / "core" / "tiles.py",
        ]
        for path in pure_core:
            imports = _imported_roots(path)
            assert not any(m.startswith("PySide6") or m.startswith("app.gui") for m in imports), (
                f"{path.name} 不应依赖 PySide6 或 app.gui: {imports}"
            )

    def test_entire_core_layer_never_imports_gui_or_qtwidgets(self):
        for py in (APP_ROOT / "core").rglob("*.py"):
            imports = _imported_roots(py)
            forbidden = [
                m for m in imports
                if m.startswith("app.gui") or m.startswith("PySide6.QtWidgets") or m.startswith("PySide6.QtGui")
            ]
            assert not forbidden, f"{py.relative_to(REPO_ROOT)} 不应依赖 GUI/QtWidgets: {forbidden}"

    def test_platform_layer_does_not_import_gui(self):
        for py in (APP_ROOT / "platform").glob("*.py"):
            imports = _imported_roots(py)
            assert not any(m.startswith("app.gui") for m in imports), (
                f"{py.name} 不应反向依赖 app.gui: {imports}"
            )

    def test_styles_layer_does_not_import_gui(self):
        for py in (APP_ROOT / "styles").glob("*.py"):
            imports = _imported_roots(py)
            assert not any(m.startswith("app.gui") for m in imports), (
                f"{py.name} 不应反向依赖 app.gui: {imports}"
            )


class TestQssSeparation:
    """验证外部 QSS 模板完整性与 GUI 模块禁止零散静态内联 QSS。"""

    def test_all_qss_templates_exist_and_compile_cleanly(self, qapp):
        expected = {"common", "menu", "hover_panel", "settings", "dialogs", "buttons_inputs"}
        qss_dir = APP_ROOT / "styles" / "qss"
        actual = {p.stem for p in qss_dir.glob("*.qss")}
        assert expected.issubset(actual)

        for dark in (True, False):
            for scale in (1.0, 1.5):
                compiled_outputs = [
                    qss_engine.compile_qss("common", dark=dark, scale=scale),
                    theme.menu_qss(dark, scale),
                    theme.hover_panel_qss(dark, scale),
                    theme.settings_qss(dark, int(round(18 * scale)), scale),
                    theme.dialog_qss(dark, scale),
                ]
                for out in compiled_outputs:
                    assert out.strip()
                    assert "{{" not in out and "}}" not in out

    def test_no_scattered_inline_qss_in_gui_layer(self):
        # 仅允许顶层窗口/菜单/Toast 挂载编译后的外部 QSS，以及用户任意 HEX 取色预览按钮
        allowed_files = {
            "app/gui/hover_panel/panel.py",
            "app/gui/settings/dialog.py",
            "app/gui/settings/coding_plan_dialog.py",
            "app/gui/settings/pages/bar_style_page.py",
            "app/gui/taskbar/menu_builder.py",
            "app/gui/widgets/motion.py",
        }
        offenders: list[str] = []
        pattern = re.compile(r"\.setStyleSheet\(")
        for py in (APP_ROOT / "gui").rglob("*.py"):
            rel = py.relative_to(REPO_ROOT).as_posix()
            if rel in allowed_files:
                continue
            text = py.read_text(encoding="utf-8")
            if pattern.search(text):
                offenders.append(rel)
        assert offenders == [], f"以下 GUI 文件出现未外置的 setStyleSheet 调用: {offenders}"


class TestDesignPatternContracts:
    """验证核心设计模式（视图策略注册表、卡片注册表、设置页组合器）契约。"""

    def test_bar_view_registry_has_default_strategies(self):
        from app.gui.taskbar.views import (
            VIEW_QUOTA,
            VIEW_SCHEDULE,
            VIEW_SYSTEM,
            VIEW_WEATHER,
            build_default_view_registry,
        )

        reg = build_default_view_registry()
        for vid in (VIEW_SCHEDULE, VIEW_SYSTEM, VIEW_WEATHER, VIEW_QUOTA):
            assert reg.get(vid) is not None, f"缺少视图策略: {vid}"

    def test_panel_card_registry_covers_all_default_panel_cards(self):
        from app.gui.hover_panel.registry import build_default_card_registry

        reg = build_default_card_registry()
        default_ids = [c["id"] for c in config_mod.DEFAULT_PANEL_CARDS]
        for cid in default_ids:
            assert reg.get(cid) is not None, f"DEFAULT_PANEL_CARDS 中的卡片 {cid} 未在 PanelCardRegistry 注册"

    def test_settings_dialog_composes_six_base_pages(self, qapp):
        from app.gui.settings import BaseSettingsPage, SettingsDialog

        cfg = copy.deepcopy(config_mod.DEFAULT_CONFIG)
        dlg = SettingsDialog(None, cfg)
        assert len(dlg._pages) == 6
        assert all(isinstance(p, BaseSettingsPage) for p in dlg._pages)
        assert dlg._seg.count() == len(dlg._pages)
        dlg.deleteLater()


class TestUserPluginCompatibility:
    """验证用户自定义插件旧导入路径 app.sources / app.tiles 与核心单例严格等价。"""

    def test_legacy_plugin_aliases_are_identical_singletons(self):
        import app.core.sources as core_sources
        import app.core.tiles as core_tiles
        import app.sources as legacy_sources
        import app.tiles as legacy_tiles

        assert legacy_sources is core_sources
        assert legacy_tiles is core_tiles
        assert legacy_sources.SOURCES is core_sources.SOURCES
        assert legacy_tiles.make_tile is core_tiles.make_tile
