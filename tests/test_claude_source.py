"""tests/test_claude_source.py — Anthropic / Claude Code 数据源单元测试（纯 Mock 无网络依赖）。"""

import json
from pathlib import Path
import pytest

from app.core.quota_api import QuotaError
from app.core.sources import claude_source, get_source, quota_source


def test_claude_source_registration():
    info = claude_source.CLAUDE_SOURCE_INFO
    assert info is not None
    assert info.id == "claude_quota"
    assert info.kind == "remote"
    assert info.needs_credentials is True


def test_parse_anthropic_rate_limits():
    headers = {
        "anthropic-ratelimit-tokens-limit": "100000",
        "anthropic-ratelimit-tokens-remaining": "75000",
        "anthropic-ratelimit-tokens-reset": "2026-10-28T10:00:00Z",
        "anthropic-ratelimit-requests-limit": "500",
        "anthropic-ratelimit-requests-remaining": "450",
        "anthropic-ratelimit-requests-reset": "2026-10-28T10:00:00Z",
    }
    windows = claude_source.parse_anthropic_rate_limits(headers)
    assert len(windows) == 2

    tok_w = next(w for w in windows if w["kind"] == "tokens")
    assert tok_w["total"] == 100000.0
    assert tok_w["remaining"] == 75000.0
    assert tok_w["remaining_percent"] == 75.0
    assert tok_w["percent"] == 25.0
    assert tok_w["reset_ms"] is not None

    req_w = next(w for w in windows if w["kind"] == "requests")
    assert req_w["total"] == 500.0
    assert req_w["remaining"] == 450.0
    assert req_w["remaining_percent"] == 90.0
    assert req_w["percent"] == 10.0


def test_parse_claude_usage_dict():
    raw_data = {
        "name": "Claude-Work",
        "plan": "Claude Pro",
        "used_tokens": 20000,
        "limit_tokens": 100000,
        "cost_usd": 3.5,
        "cost_limit": 20.0,
    }
    res = claude_source.parse_claude_usage_dict(raw_data)
    assert res["id"] == "claude"
    assert res["name"] == "Claude-Work"
    assert res["plan"] == "Claude Pro"
    assert res["cost_usd"] == 3.5
    assert len(res["windows"]) >= 1

    win = res["windows"][0]
    assert win["kind"] == "tokens"
    assert win["remaining_percent"] == 80.0
    assert win["remaining"] == 80000.0


def test_discover_claude_auth_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-secret-123")
    auth = claude_source.discover_claude_auth()
    assert auth is not None
    assert auth["apiKey"] == "sk-ant-env-secret-123"
    assert auth["source"] == "env"


def test_discover_claude_auth_from_file(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake_claude_json = tmp_path / ".claude.json"
    fake_claude_json.write_text(json.dumps({"apiKey": "sk-ant-file-456"}), encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    auth = claude_source.discover_claude_auth()
    assert auth is not None
    assert auth["apiKey"] == "sk-ant-file-456"


def test_fetch_claude_usage_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(claude_source, "discover_claude_auth", lambda: None)
    with pytest.raises(QuotaError, match="未配置 Claude / Anthropic API Key"):
        claude_source.fetch_claude_usage("")


def test_fetch_claude_tiles_fallback():
    cfg = {"sources": {"claude_quota": {"apiKey": ""}}}
    tiles = claude_source.fetch_claude_tiles(cfg)
    assert len(tiles) >= 1
    assert tiles[0]["id"] == "claude:tokens"
    assert tiles[0]["source"] == "claude_quota"


def test_claude_provider_dispatch(monkeypatch):
    called = {}

    def mock_fetch(api_key, base_url="", timeout=6.0):
        called["key"] = api_key
        return {
            "id": "claude",
            "provider": "claude",
            "name": "Claude",
            "plan": "API",
            "windows": [],
        }

    monkeypatch.setattr(claude_source, "fetch_claude_usage", mock_fetch)

    item = {
        "provider": "claude",
        "name": "MyClaude",
        "apiKey": "sk-ant-direct",
    }
    res = quota_source.dispatch_provider_quota(item)
    assert called["key"] == "sk-ant-direct"
    assert res["name"] == "MyClaude"
