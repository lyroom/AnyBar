"""tests/test_sources.py — 数据源注册表与 Provider 分派单元测试。"""

import pytest

from app.core import quota_api, sources
from app.core.sources import quota_source


def test_source_info_and_registry():
    info = sources.SourceInfo(
        id="test_src",
        title="测试源",
        kind="local",
        default_interval_sec=5,
    )

    @sources.register(info)
    def dummy_fetch(cfg, timeout=8.0):
        return [{"id": "t1", "source": "test_src", "name": "Item"}]

    reg = sources.get_source("test_src")
    assert reg is not None
    assert reg.info.id == "test_src"
    assert reg.info.title == "测试源"
    assert reg.info.kind == "local"
    assert reg.info.default_interval_sec == 5
    items = reg.fetch_fn({})
    assert len(items) == 1
    assert items[0]["id"] == "t1"

    # 清理测试源
    sources.unregister("test_src")
    assert sources.get_source("test_src") is None


def test_quota_source_registered():
    reg = sources.get_source("quota")
    assert reg is not None
    assert reg.info.id == "quota"
    assert reg.info.kind == "remote"
    assert reg.info.needs_credentials is True


def test_provider_specs_and_compatibility():
    # 验证 quota_api.PROVIDER_TYPES 包含预期的 8 种渠道
    prov_keys = [k for k, _ in quota_api.PROVIDER_TYPES]
    assert "magpie" in prov_keys
    assert "deepseek" in prov_keys
    assert "codex" in prov_keys
    assert "glm" in prov_keys
    assert "kimi" in prov_keys
    assert "openrouter" in prov_keys
    assert "newapi" in prov_keys
    assert "manual" in prov_keys

    # 检查 handlers 映射表
    assert "deepseek" in quota_source.PROVIDER_HANDLERS
    assert "kimi" in quota_source.PROVIDER_HANDLERS
    assert "moonshot" in quota_source.PROVIDER_HANDLERS
    assert "glm" in quota_source.PROVIDER_HANDLERS


def test_dispatch_unknown_provider():
    with pytest.raises(quota_api.QuotaError, match="不支持自动查询"):
        quota_source.dispatch_provider_quota({"provider": "unknown_provider_xyz"})


def test_dispatch_mock_provider(monkeypatch):
    called = {}

    def mock_deepseek(item, key, base_url, name, timeout):
        called["key"] = key
        called["name"] = name
        return {"balance": "100.00"}

    monkeypatch.setitem(quota_source.PROVIDER_HANDLERS, "deepseek", mock_deepseek)

    res = quota_api.fetch_provider_quota({
        "provider": "deepseek",
        "apiKey": "sk-test-123",
        "name": "MyDeepSeek",
    })

    assert called["key"] == "sk-test-123"
    assert called["name"] == "MyDeepSeek"
    assert res["balance"] == "100.00"
    assert res["name"] == "MyDeepSeek"


def test_system_source_registered():
    reg = sources.get_source("system")
    assert reg is not None
    assert reg.info.id == "system"
    assert reg.info.kind == "local"
    assert reg.info.default_interval_sec == 2
    assert reg.info.needs_credentials is False

    tiles = reg.fetch_fn({})
    assert len(tiles) == 3
    ids = [t["id"] for t in tiles]
    assert "system:cpu" in ids
    assert "system:mem" in ids
    assert "system:disk" in ids
    for t in tiles:
        assert 0.0 <= t["ratio"] <= 1.0
        assert t["kind"] == "ring"
