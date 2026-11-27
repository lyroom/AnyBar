"""tests/test_user_plugins.py — 用户第三方插件动态加载机制测试。"""

from pathlib import Path
import pytest

from app.core.sources import SOURCES, get_source, get_user_plugins_dir, load_user_plugins, unregister


def test_get_user_plugins_dir():
    p = get_user_plugins_dir()
    assert isinstance(p, Path)
    assert "plugins" in str(p).lower()


def test_load_user_plugins_sample_creation(tmp_path):
    assert not tmp_path.exists() or len(list(tmp_path.iterdir())) == 0
    loaded = load_user_plugins(plugins_dir=tmp_path)
    assert loaded == []
    sample = tmp_path / "example_source.py.sample"
    assert sample.exists()
    assert "SourceInfo" in sample.read_text(encoding="utf-8")


def test_load_valid_user_plugin(tmp_path):
    plugin_code = '''
from app.sources import SourceInfo, register
from app.tiles import make_tile

@register(
    SourceInfo(
        id="test_custom_metric",
        title="测试自定义指标",
        kind="local",
        default_interval_sec=15,
    )
)
def fetch_custom(cfg: dict, timeout: float = 2.0):
    return [
        make_tile(
            id="custom:1",
            source="test_custom_metric",
            name="Custom",
            ratio=0.5,
            center_text="50%",
        )
    ]
'''
    py_file = tmp_path / "custom_test.py"
    py_file.write_text(plugin_code, encoding="utf-8")

    try:
        loaded = load_user_plugins(plugins_dir=tmp_path)
        assert "custom_test" in loaded

        reg = get_source("test_custom_metric")
        assert reg is not None
        assert reg.info.title == "测试自定义指标"
        tiles = reg.fetch_fn({})
        assert len(tiles) == 1
        assert tiles[0]["center_text"] == "50%"
    finally:
        unregister("test_custom_metric")


def test_load_invalid_plugin_graceful(tmp_path):
    py_file = tmp_path / "broken_plugin.py"
    py_file.write_text("this is invalid python syntax syntax error !!!", encoding="utf-8")

    loaded = load_user_plugins(plugins_dir=tmp_path)
    assert "broken_plugin" not in loaded
