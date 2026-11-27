"""tests/test_source_service.py — SourceService 调度算法单元测试。"""

import pytest

from app.core.source_service import compute_due_sources


def test_compute_due_sources():
    now = 1000.0
    schedules = {
        # 1. 已到期：上次运行是 900，间隔 60 -> 900+60 <= 1000
        "s1": {"enabled": True, "interval_sec": 60, "last_run_ts": 900.0},
        # 2. 未到期：上次运行是 980，间隔 60 -> 980+60 > 1000
        "s2": {"enabled": True, "interval_sec": 60, "last_run_ts": 980.0},
        # 3. 禁用中：即使时间已经超时，也不触发
        "s3": {"enabled": False, "interval_sec": 10, "last_run_ts": 900.0},
        # 4. 首次运行：last_run_ts 为 0
        "s4": {"enabled": True, "interval_sec": 30, "last_run_ts": 0.0},
    }

    due = compute_due_sources(schedules, now)
    assert "s1" in due
    assert "s2" not in due
    assert "s3" not in due
    assert "s4" in due


def test_compute_due_sources_min_interval():
    now = 100.0
    # 间隔为 0 时钳制为最小 1 秒
    schedules = {
        "fast": {"enabled": True, "interval_sec": 0, "last_run_ts": 99.5},
    }
    # 仅过了 0.5s，应当不到期
    due = compute_due_sources(schedules, now)
    assert "fast" not in due

    # 过了 1.1s，应当到期
    due_later = compute_due_sources(schedules, now + 0.6)
    assert "fast" in due_later


def test_source_service_replay_states(qapp, monkeypatch):
    from app.core.source_service import SourceService
    from app.core import config

    monkeypatch.setattr(SourceService, "_run_source_async", lambda self, reg: None)
    cfg = config.load_config()
    service = SourceService(cfg)
    try:
        received = []
        service.updated.connect(lambda s: received.append(s["source"]))

        service.replay_states()
        assert "system" in received
    finally:
        service.shutdown()


def test_source_service_shutdown(qapp, monkeypatch):
    from app.core.source_service import SourceService
    from app.core import config

    monkeypatch.setattr(SourceService, "_run_source_async", lambda self, reg: None)
    cfg = config.load_config()
    service = SourceService(cfg)
    assert service._scheduler_timer.isActive()
    service.shutdown()
    assert not service._scheduler_timer.isActive()
    assert service._disposed is True

    # 处置后安全 emit 不再发出信号
    emitted = []
    service.updated.connect(lambda s: emitted.append(s))
    service._safe_emit({"test": 1})
    assert len(emitted) == 0
