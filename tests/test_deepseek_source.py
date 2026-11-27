"""tests/test_deepseek_source.py — DeepSeek 与 OpenAI 数据源单元测试（纯 Mock 无网络依赖）。"""

import pytest

from app.core.quota_api import QuotaError
from app.core.sources import deepseek_source, get_source, quota_source


def test_deepseek_source_registration():
    info = deepseek_source.DEEPSEEK_SOURCE_INFO
    assert info is not None
    assert info.id == "deepseek_quota"
    assert info.kind == "remote"
    assert info.needs_credentials is True


def test_parse_deepseek_balance_cny():
    raw_data = {
        "is_available": True,
        "balance_infos": [
            {
                "currency": "CNY",
                "total_balance": "28.50",
                "granted_balance": "10.00",
                "topped_up_balance": "18.50",
            }
        ],
    }
    res = deepseek_source.parse_deepseek_balance(raw_data)
    assert res["id"] == "deepseek"
    assert res["provider"] == "deepseek"
    assert res["balance"] == "¥28.50"
    assert res["total_balance"] == 28.50
    assert res["status"] == "ok"
    assert len(res["windows"]) == 1
    assert res["windows"][0]["display"] == "¥28.50"


def test_parse_openai_usage():
    sub_data = {
        "plan": {"title": "Team Plan"},
        "hard_limit_usd": 100.0,
        "soft_limit_usd": 80.0,
    }
    usage_data = {
        "total_usage": 3500.0,  # 3500 cents = $35.00
    }
    res = deepseek_source.parse_openai_usage(sub_data, usage_data)
    assert res["id"] == "openai"
    assert res["provider"] == "openai"
    assert res["used"] == 35.0
    assert res["limit"] == 100.0
    assert res["remaining"] == 65.0
    assert len(res["windows"]) == 1

    win = res["windows"][0]
    assert win["name"] == "月度 Cap 额度"
    assert win["percent"] == 35.0
    assert win["remaining_percent"] == 65.0
    assert "$35.00 / $100.00" in win["display"]


def test_parse_openai_ratelimits():
    headers = {
        "x-ratelimit-limit-tokens": "50000",
        "x-ratelimit-remaining-tokens": "40000",
        "x-ratelimit-limit-requests": "200",
        "x-ratelimit-remaining-requests": "180",
    }
    windows = deepseek_source.parse_openai_ratelimits(headers)
    assert len(windows) == 2

    tok_w = next(w for w in windows if w["kind"] == "tokens")
    assert tok_w["total"] == 50000.0
    assert tok_w["remaining"] == 40000.0
    assert tok_w["remaining_percent"] == 80.0
    assert tok_w["percent"] == 20.0

    req_w = next(w for w in windows if w["kind"] == "requests")
    assert req_w["total"] == 200.0
    assert req_w["remaining"] == 180.0
    assert req_w["remaining_percent"] == 90.0


def test_fetch_openai_usage_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(QuotaError, match="未配置 OpenAI API Key"):
        deepseek_source.fetch_openai_usage("")


def test_fetch_deepseek_tiles_fallback():
    cfg = {"sources": {"deepseek_quota": {"apiKey": ""}}}
    tiles = deepseek_source.fetch_deepseek_tiles(cfg)
    assert len(tiles) >= 1
    assert tiles[0]["id"] == "deepseek:bal"
    assert tiles[0]["source"] == "deepseek_quota"


def test_openai_provider_dispatch(monkeypatch):
    called = {}

    def mock_fetch(api_key, base_url="", timeout=6.0):
        called["key"] = api_key
        return {
            "id": "openai",
            "provider": "openai",
            "name": "OpenAI",
            "plan": "API",
            "windows": [],
        }

    monkeypatch.setattr(deepseek_source, "fetch_openai_usage", mock_fetch)

    item = {
        "provider": "openai",
        "name": "MyOpenAI",
        "apiKey": "sk-test-openai",
    }
    res = quota_source.dispatch_provider_quota(item)
    assert called["key"] == "sk-test-openai"
    assert res["name"] == "MyOpenAI"
