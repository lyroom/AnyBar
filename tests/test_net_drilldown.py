"""tests/test_net_drilldown.py — 网络占用进程下钻与 TCP 表解析测试。"""

import pytest
from app.core.sources.system_source import fetch_system_tiles, get_top_network_processes


def test_get_top_network_processes():
    # 本地原生测试：Windows 环境下应能成功读取当前进程快照
    procs = get_top_network_processes(limit=3)
    assert isinstance(procs, list)
    for p in procs:
        assert "name" in p
        assert "connections" in p
        assert isinstance(p["connections"], int)


def test_fetch_system_tiles_structure():
    cfg = {"sources": {"system": {"enabled": True}}}
    tiles = fetch_system_tiles(cfg)
    assert len(tiles) == 3
    t0 = tiles[0]
    assert "net_up_str" in t0
    assert "net_down_str" in t0
    assert "top_net_procs" in t0
