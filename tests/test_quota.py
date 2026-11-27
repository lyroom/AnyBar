# -*- coding: utf-8 -*-
"""quota_api 纯逻辑单测：响应解析 / 窗口命名 / 站点解析 / 错误码（不联网、无 GUI）。"""

import pytest

from app.core import quota_api


def _payload(limits, level="pro"):
    return {"code": 200, "msg": "success",
            "data": {"level": level, "limits": limits}}


class TestSiteRoot:
    def test_site_keys(self):
        assert quota_api.site_root("bigmodel") == "https://open.bigmodel.cn"
        assert quota_api.site_root("zai") == "https://api.z.ai"

    def test_full_anthropic_url_takes_origin(self):
        assert (quota_api.site_root("https://open.bigmodel.cn/api/anthropic")
                == "https://open.bigmodel.cn")
        assert (quota_api.site_root("https://api.z.ai/api/anthropic")
                == "https://api.z.ai")

    def test_unknown_site_rejected(self):
        with pytest.raises(quota_api.QuotaError):
            quota_api.site_root("https://evil.example.com")
        with pytest.raises(quota_api.QuotaError):
            quota_api.site_root("")


class TestParseEnvelope:
    def test_ok_codes(self):
        assert quota_api.parse_envelope({"code": 0, "data": {"a": 1}}) == {"a": 1}
        assert quota_api.parse_envelope({"code": "200", "data": {}}) == {}

    def test_error_code_raises_with_msg(self):
        with pytest.raises(quota_api.QuotaError, match="余额不足"):
            quota_api.parse_envelope({"code": 1113, "msg": "余额不足"})

    def test_non_dict_raises(self):
        with pytest.raises(quota_api.QuotaError):
            quota_api.parse_envelope("junk")


class TestWindowNaming:
    """窗口名按 unit×number 推算，接口返回顺序不保证 5h 在前。"""

    def test_unit_enum_mapping(self):
        # 1=分钟 3=小时 4=天 5=30天(月) 6=7天(周)
        assert quota_api.window_span_sec({"unit": 3, "number": 5}) == 18000
        assert quota_api.window_span_sec({"unit": 6, "number": 1}) == 604800
        assert quota_api.window_span_sec({"unit": 4, "number": 3}) == 259200
        assert quota_api.window_span_sec({"unit": 1, "number": 30}) == 1800
        assert quota_api.window_span_sec({}) == 0

    def test_team_5h_without_number(self):
        # 团队版 5 小时窗不带 count，默认按 5 小时
        assert quota_api.window_span_sec({"unit": 3}) == 18000

    def test_names_by_span(self):
        assert quota_api.window_name(18000) == "5 小时窗口"
        assert quota_api.window_name(3600) == "1 小时窗口"
        assert quota_api.window_name(7 * 86400) == "每周窗口"
        assert quota_api.window_name(30 * 86400) == "每月窗口"
        assert quota_api.window_name(3 * 86400) == "3 天窗口"
        assert quota_api.window_name(0) == "额度窗口"

    def test_order_independent_naming(self):
        # 每周窗在前、5h 窗在后，命名仍按各自 span 而非顺序
        w = quota_api.parse_quota_payload(
            {"limits": [{"type": "TOKENS_LIMIT", "unit": 6, "number": 1,
                         "percentage": 10},
                        {"type": "TOKENS_LIMIT", "unit": 3, "number": 5,
                         "percentage": 55}]})
        assert [x["name"] for x in w["windows"]] == ["每周窗口", "5 小时窗口"]
        assert w["windows"][0]["span_sec"] == 604800
        assert w["windows"][1]["span_sec"] == 18000

    def test_no_unit_falls_back_generic(self):
        w = quota_api.parse_quota_payload(
            {"limits": [{"type": "TOKENS_LIMIT", "percentage": 62}]})
        assert w["windows"][0]["name"] == "额度窗口"
        assert w["windows"][0]["span_sec"] == 0


class TestPrimaryWindow:
    def test_picks_shortest_span_tokens(self):
        wins = [
            {"kind": "tokens", "name": "每周窗口", "span_sec": 604800,
             "percent": 10.0},
            {"kind": "tokens", "name": "5 小时窗口", "span_sec": 18000,
             "percent": 95.0},
            {"kind": "mcp", "name": "MCP · 本月", "percent": 3.0},
        ]
        assert quota_api.primary_window(wins)["name"] == "5 小时窗口"

    def test_unknown_span_ranked_last(self):
        wins = [
            {"kind": "tokens", "name": "额度窗口", "span_sec": 0, "percent": 5.0},
            {"kind": "tokens", "name": "5 小时窗口", "span_sec": 18000,
             "percent": 40.0},
        ]
        assert quota_api.primary_window(wins)["name"] == "5 小时窗口"

    def test_none_without_tokens(self):
        assert quota_api.primary_window(
            [{"kind": "mcp", "percent": 3.0}]) is None
        assert quota_api.primary_window([]) is None
        assert quota_api.primary_window(None) is None


class TestParseQuotaPayload:
    def test_usage_remaining_derives_percent(self):
        w = quota_api.parse_quota_payload(
            {"level": "lite", "limits": [
                {"type": "TOKENS_LIMIT", "unit": 3, "number": 5,
                 "usage": 20, "remaining": 11.5,
                 "nextResetTime": 1761000000000}]})
        assert w["level"] == "lite"
        assert len(w["windows"]) == 1
        win = w["windows"][0]
        assert win["kind"] == "tokens"
        assert win["name"] == "5 小时窗口"
        assert win["span_sec"] == 18000
        assert win["used"] == pytest.approx(8.5)
        assert win["total"] == 20.0
        assert win["percent"] == pytest.approx(42.5)
        assert win["reset_ms"] == 1761000000000

    def test_current_value_only(self):
        w = quota_api.parse_quota_payload(
            {"limits": [{"type": "TIME_LIMIT", "currentValue": 3, "usage": 100}]})
        win = w["windows"][0]
        assert win["kind"] == "mcp"
        assert win["name"] == "MCP · 本月"
        assert win["used"] == 3.0
        assert win["percent"] == 3.0

    def test_percentage_only(self):
        w = quota_api.parse_quota_payload(
            {"limits": [{"type": "TOKENS_LIMIT", "percentage": 62.34}]})
        assert w["windows"][0]["percent"] == 62.3
        assert w["windows"][0]["used"] is None

    def test_string_numbers_accepted(self):
        w = quota_api.parse_quota_payload(
            {"limits": [{"type": "TOKENS_LIMIT", "usage": "20",
                         "remaining": "5"}]})
        assert w["windows"][0]["percent"] == 75.0

    def test_empty_and_garbage_limits(self):
        assert quota_api.parse_quota_payload({}) == {"level": "", "windows": []}
        w = quota_api.parse_quota_payload({"limits": ["junk", None, {}]})
        assert w["windows"] == []

    def test_zero_usage_window_kept_with_percent_none(self):
        w = quota_api.parse_quota_payload(
            {"limits": [{"type": "TOKENS_LIMIT", "usage": 0,
                         "percentage": 100}]})
        # usage=0 视为无上限旧套餐：仅取 percentage 展示
        assert w["windows"][0]["percent"] == 100.0


class TestFetchQuotaInputValidation:
    def test_empty_key_raises(self):
        with pytest.raises(quota_api.QuotaError, match="API Key"):
            quota_api.fetch_quota("bigmodel", "  ")


class TestTeamContext:
    def test_url_and_headers(self):
        team = {"org": "org-1", "project": "proj_1"}
        assert (quota_api.quota_limit_url("https://open.bigmodel.cn", team)
                == "https://open.bigmodel.cn/api/monitor/usage/quota/limit?type=2")
        assert (quota_api.quota_limit_url("https://open.bigmodel.cn", None)
                == "https://open.bigmodel.cn/api/monitor/usage/quota/limit")
        h = quota_api.team_headers(team)
        assert h == {"Bigmodel-Organization": "org-1",
                     "Bigmodel-Project": "proj_1"}
        # 空白 ID 产出空头，fetch_quota 会拦下
        assert not quota_api.team_headers({"org": " ", "project": ""})[
            "Bigmodel-Organization"]

    def test_fetch_quota_team_requires_ids(self):
        with pytest.raises(quota_api.QuotaError, match="组织/项目"):
            quota_api.fetch_quota("bigmodel", "some-key",
                                  team={"org": "", "project": "p"})

    def _write_creds(self, path, keys):
        import json as _json
        path.mkdir(parents=True, exist_ok=True)
        (path / "credentials.json").write_text(
            _json.dumps(keys), encoding="utf-8")

    def test_discover_team_from_zcode_credentials(self, tmp_path):
        import urllib.parse
        team_entry = urllib.parse.quote(
            '["https://bigmodel.cn","bigmodel","7411",'
            '{"organizationId":"org-ABC","projectId":"proj_XYZ"},1,null]')
        self._write_creds(tmp_path, {
            "oauth:bigmodel:access_token": "enc:v1",
            f"project-key-location:v1:{team_entry}": "enc:v2",
        })
        found = quota_api.discover_team_context(zcode_dir=tmp_path)
        assert found == {"org": "org-ABC", "project": "proj_XYZ"}

    def test_discover_prefers_matching_site(self, tmp_path):
        import urllib.parse
        zai_entry = urllib.parse.quote(
            '["https://z.ai","zai","1",'
            '{"organizationId":"org-ZAI","projectId":"proj_ZAI"},1,null]')
        bm_entry = urllib.parse.quote(
            '["https://bigmodel.cn","bigmodel","1",'
            '{"organizationId":"org-BM","projectId":"proj_BM"},1,null]')
        self._write_creds(tmp_path, {
            f"project-key-location:v1:{zai_entry}": "e",
            f"project-key-location:v1:{bm_entry}": "e",
        })
        assert quota_api.discover_team_context(
            zcode_dir=tmp_path, base="bigmodel")["org"] == "org-BM"
        assert quota_api.discover_team_context(
            zcode_dir=tmp_path, base="zai")["org"] == "org-ZAI"

    def test_discover_ignores_non_team_and_missing(self, tmp_path):
        import urllib.parse
        personal = urllib.parse.quote(
            '["https://bigmodel.cn","bigmodel","1","non-team",1,null]')
        self._write_creds(tmp_path, {
            f"project-key-location:v1:{personal}": "e",
            "project-key-location:v1:not-json": "e",
        })
        assert quota_api.discover_team_context(zcode_dir=tmp_path) is None
        # 文件不存在 / 坏 JSON → None，不抛
        assert quota_api.discover_team_context(
            zcode_dir=tmp_path / "nope") is None
        (tmp_path / "credentials.json").write_text("{broken", encoding="utf-8")
        assert quota_api.discover_team_context(zcode_dir=tmp_path) is None


class TestMagpieQuotas:
    def test_parse_magpie_list_and_cache(self):
        items = [
            {
                "provider": "zcode",
                "account": "user1",
                "plan_type": "团队套餐标准版",
                "windows": [
                    {"label": "5h", "used": 27, "limit": 100, "reset_at": "2026-10-26T12:00:00Z"},
                    {"label": "7d", "used": 7, "limit": 100},
                ],
            },
            {
                "provider": "codex",
                "account": "test@gmail.com",
                "plan_type": "plus",
                "windows": [
                    {"label": "5 hours", "used": 14, "limit": 100},
                    {"label": "7 days", "used": 32, "limit": 100},
                ],
            },
        ]
        cards = quota_api.parse_magpie_quotas(items)
        assert len(cards) == 2
        assert cards[0]["provider"] == "zcode"
        assert cards[0]["title"] == "ZCode"
        assert cards[0]["windows"][0]["percent"] == 27.0
        assert cards[1]["provider"] == "codex"
        assert cards[1]["title"] == "Codex"
        assert cards[1]["windows"][0]["percent"] == 14.0

    def test_filter_providers(self):
        items = [
            {"provider": "zcode", "windows": [{"label": "5h", "used": 10, "limit": 100}]},
            {"provider": "codex", "windows": [{"label": "5h", "used": 20, "limit": 100}]},
        ]
        cards = quota_api.parse_magpie_quotas(items, providers_filter=["codex"])
        assert len(cards) == 1
        assert cards[0]["provider"] == "codex"

