"""tests/test_tiles.py — app.tiles 模块的纯逻辑单元测试。"""

import pytest

from app.core import tiles


def test_fmt_num():
    assert tiles.fmt_num(100) == "100"
    assert tiles.fmt_num(99.4) == "99.4"
    assert tiles.fmt_num(100.0) == "100"
    assert tiles.fmt_num(12000) == "12k"
    assert tiles.fmt_num(12500) == "12.5k"
    assert tiles.fmt_num(150000) == "150k"
    assert tiles.fmt_num("unknown") == "unknown"


def test_ratio_to_color():
    pal = {"quota_green": "#GREEN", "quota_amber": "#AMBER", "quota_red": "#RED"}
    assert tiles.ratio_to_color(0.8, pal) == "#GREEN"
    assert tiles.ratio_to_color(0.51, pal) == "#GREEN"
    assert tiles.ratio_to_color(0.50, pal) == "#AMBER"
    assert tiles.ratio_to_color(0.21, pal) == "#AMBER"
    assert tiles.ratio_to_color(0.20, pal) == "#RED"
    assert tiles.ratio_to_color(0.0, pal) == "#RED"


def test_make_tile():
    t = tiles.make_tile(
        id="cpu",
        source="system",
        name="CPU",
        ratio=0.45,
        center_text="45%",
        sub_text="16核",
    )
    assert t["id"] == "cpu"
    assert t["source"] == "system"
    assert t["name"] == "CPU"
    assert t["ratio"] == 0.45
    assert t["frac"] == 0.45
    assert t["pct"] == "45%"
    assert t["center_text"] == "45%"
    assert t["sub_text"] == "16核"
    assert t["color"] == "#FF9500"  # 0.45 处于 0.20~0.50，为琥珀色
    assert t["kind"] == "ring"


def test_find_primary_window():
    assert tiles.find_primary_window(None) is None
    assert tiles.find_primary_window([]) is None

    wins = [
        {"kind": "requests", "percent": 50, "span_sec": 3600},
        {"kind": "tokens", "percent": 80, "span_sec": 86400},
        {"kind": "tokens", "percent": 20, "span_sec": 18000},  # 5h 最短
    ]
    best = tiles.find_primary_window(wins)
    assert best is not None
    assert best["span_sec"] == 18000


def test_card_to_tile():
    card_with_win = {
        "provider": "glm",
        "name": "GLM-4",
        "windows": [
            {
                "kind": "tokens",
                "percent": 30,
                "remaining_percent": 70,
                "remaining": 70000,
                "total": 100000,
                "span_sec": 18000,
            }
        ],
    }
    t1 = tiles.card_to_tile(card_with_win)
    assert t1 is not None
    assert t1["name"] == "GLM-4"
    assert t1["ratio"] == 0.7
    assert t1["center_text"] == "70%"
    assert t1["sub_text"] == "70k/100k"
    assert t1["color"] == "#34C759"

    card_with_bal = {
        "provider": "deepseek",
        "name": "DeepSeek",
        "balance": "¥58.20",
    }
    t2 = tiles.card_to_tile(card_with_bal)
    assert t2 is not None
    assert t2["center_text"] == "¥"
    assert t2["sub_text"] == "¥58.20"


def test_tiles_from_quota_state_user_quotas():
    cfg = {
        "quotas": [
            {"name": "VIP", "used": 80, "limit": 100},
            {"name": "Bal", "balance": "12.5"},
            {"name": ""},  # 空名称应被过滤
        ]
    }
    st = {"row_updates": {0: {"used": 20}}}  # 实时更新覆盖
    ts = tiles.tiles_from_quota_state(st, cfg)
    assert len(ts) == 2
    assert ts[0]["name"] == "VIP"
    assert ts[0]["ratio"] == 0.2  # 20/100
    assert ts[0]["center_text"] == "20%"
    assert ts[1]["name"] == "Bal"
    assert ts[1]["center_text"] == "¥"
    assert ts[1]["sub_text"] == "¥12.5"


def test_tiles_from_quota_state_auto_fallback():
    cfg = {
        "quotas": [],
        "quotaApi": {"enabled": True, "showOnBar": True},
    }
    st = {
        "cards": [
            {
                "name": "GLM",
                "windows": [{"kind": "tokens", "percent": 10, "span_sec": 18000}],
            },
            {"name": "Kimi", "balance": "$5.00"},
        ]
    }
    ts = tiles.tiles_from_quota_state(st, cfg)
    assert len(ts) == 2
    assert ts[0]["name"] == "GLM"
    assert ts[0]["ratio"] == 0.9  # 100 - 10 = 90%
    assert ts[1]["name"] == "Kimi"
    assert ts[1]["center_text"] == "$"
