"""tests/test_cursor_source.py — Cursor 数据源单元测试（纯 Mock 无网络依赖）。"""

import json
from pathlib import Path
import pytest

from app.core.quota_api import QuotaError
from app.core.sources import cursor_source, get_source, quota_source


def test_cursor_source_registration():
    info = cursor_source.CURSOR_SOURCE_INFO
    assert info is not None
    assert info.id == "cursor_quota"
    assert info.kind == "remote"
    assert info.needs_credentials is True


def test_parse_cursor_usage_pro():
    raw_data = {
        "gpt4": {
            "numRequests": 340,
            "maxRequestUsage": 500,
            "numSlowRequests": 12,
        },
        "startOfMonth": "2026-10-01T00:00:00.000Z",
        "membershipType": "pro",
    }
    res = cursor_source.parse_cursor_usage(raw_data)
    assert res["id"] == "cursor"
    assert res["provider"] == "cursor"
    assert res["plan"] == "Cursor Pro"
    assert res["level"] == "Pro"
    assert res["used"] == 340
    assert res["limit"] == 500
    assert res["remaining"] == 160
    assert res["unit"] == "req"
    assert len(res["windows"]) == 2

    fast_win = res["windows"][0]
    assert fast_win["name"] == "Fast Requests"
    assert fast_win["remaining_percent"] == 32.0
    assert fast_win["used_percent"] == 68.0
    assert fast_win["display"] == "160/500 req"
    assert fast_win["reset_ms"] is not None

    slow_win = res["windows"][1]
    assert slow_win["name"] == "Slow Requests"
    assert slow_win["used"] == 12


def test_discover_cursor_session_env(monkeypatch):
    monkeypatch.setenv("CURSOR_SESSION_TOKEN", "user_abc::jwt_123")
    tok = cursor_source.discover_cursor_session()
    assert tok == "user_abc::jwt_123"


def test_discover_cursor_session_file(tmp_path, monkeypatch):
    monkeypatch.delenv("CURSOR_SESSION_TOKEN", raising=False)
    fake_appdata = tmp_path / "AppData" / "Roaming"
    fake_storage = fake_appdata / "Cursor" / "User" / "globalStorage" / "storage.json"
    fake_storage.parent.mkdir(parents=True, exist_ok=True)
    fake_storage.write_text(
        json.dumps({"cursorAuth/sessionToken": "workos_token_xyz"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("APPDATA", str(fake_appdata))

    tok = cursor_source.discover_cursor_session()
    assert tok == "workos_token_xyz"


def test_fetch_cursor_usage_missing_token(monkeypatch):
    monkeypatch.delenv("CURSOR_SESSION_TOKEN", raising=False)
    monkeypatch.setattr(cursor_source, "discover_cursor_session", lambda: None)
    with pytest.raises(QuotaError, match="未配置 Cursor Session Token"):
        cursor_source.fetch_cursor_usage("")


def test_fetch_cursor_tiles_fallback():
    cfg = {"sources": {"cursor_quota": {"sessionToken": ""}}}
    tiles = cursor_source.fetch_cursor_tiles(cfg)
    assert len(tiles) >= 1
    assert tiles[0]["id"] == "cursor:fast"
    assert tiles[0]["source"] == "cursor_quota"


def test_cursor_provider_dispatch(monkeypatch):
    called = {}

    def mock_fetch(session_token="", timeout=6.0):
        called["token"] = session_token
        return {
            "id": "cursor",
            "provider": "cursor",
            "name": "Cursor",
            "plan": "Pro",
            "windows": [],
        }

    monkeypatch.setattr(cursor_source, "fetch_cursor_usage", mock_fetch)

    item = {
        "provider": "cursor",
        "name": "MyCursor",
        "apiKey": "sess_key_123",
    }
    res = quota_source.dispatch_provider_quota(item)
    assert called["token"] == "sess_key_123"
    assert res["name"] == "MyCursor"
