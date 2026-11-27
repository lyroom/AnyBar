"""app/source_service.py — 多源分时轮询调度服务

管理所有已注册的 SourceModule（包括 quota、系统监控等），
按照 per-source interval 计算到期时间，分时异步派发，
错误态保留旧值，经 Qt Signal(dict) 回投主线程。
"""

from __future__ import annotations

import threading
import time
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from app.core import sources
from app.core.logger import get_logger

_logger = get_logger("anybar.sources", "sources.log")


def compute_due_sources(
    schedules: dict[str, dict[str, Any]],
    now: float,
) -> list[str]:
    """纯函数：根据当前时间计算已到期需要拉取的数据源 ID 列表。"""
    due = []
    for s_id, s_info in schedules.items():
        if not s_info.get("enabled", True):
            continue
        interval = max(1.0, float(s_info.get("interval_sec", 60.0)))
        last_run = float(s_info.get("last_run_ts", 0.0))
        if now - last_run >= interval:
            due.append(s_id)
    return due


class SourceService(QObject):
    """多源调度引擎：分时轮询已启用的数据源，隔离网络抖动与本地高频刷新。"""

    updated = Signal(dict)

    def __init__(self, cfg: dict[str, Any], parent: QObject | None = None):
        super().__init__(parent)
        self._cfg = cfg
        self._schedules: dict[str, dict[str, Any]] = {}
        self._states: dict[str, dict[str, Any]] = {}
        self._busy_sources: set[str] = set()
        self._lock = threading.Lock()
        self._disposed = False

        # 调度轮询定时器（每秒检查一次到期源）
        self._scheduler_timer = QTimer(self)
        self._scheduler_timer.setInterval(1000)
        self._scheduler_timer.timeout.connect(self._on_tick)

        self._load_cached_states(cfg)
        self.configure(cfg)
        self._scheduler_timer.start()

    def shutdown(self) -> None:
        """停止调度定时器并标记已处置，阻止后续 worker emit。"""
        self._disposed = True
        if hasattr(self, "_scheduler_timer") and self._scheduler_timer.isActive():
            self._scheduler_timer.stop()

    def _load_cached_states(self, cfg: dict[str, Any]) -> None:
        """启动时用磁盘缓存预置远程源状态，先出图，网络结果回来后再刷新。"""
        for reg in sources.list_sources():
            loader = getattr(reg.info, "cache_loader", None)
            if loader is None:
                continue
            try:
                hit = loader(cfg)
            except Exception as e:  # 缓存损坏不应影响启动
                _logger.info("cache load [%s] err: %s", reg.info.id, str(e)[:120])
                continue
            if not hit:
                continue
            tiles, ts = hit
            with self._lock:
                self._states[reg.info.id] = {
                    "source": reg.info.id,
                    "state": "ok",
                    "ts": float(ts),
                    "tiles": tiles,
                    "cached": True,
                }

    def configure(self, cfg: dict[str, Any]) -> None:
        """根据配置更新各源的调度计划与启用状态。"""
        self._cfg = cfg
        src_cfg = cfg.get("sources") or {}

        # 遍历已注册的所有源
        for reg in sources.list_sources():
            s_id = reg.info.id
            s_conf = src_cfg.get(s_id, {})
            enabled = bool(s_conf.get("enabled", True))
            interval = int(s_conf.get("intervalSec", reg.info.default_interval_sec))
            interval = max(reg.info.min_interval_sec, interval)

            # 对 quota 源做特殊配置感知（保持与旧 quotaApi 兼容）
            if s_id == "quota":
                qa = cfg.get("quotaApi") or {}
                source_type = str(qa.get("source", "glm"))
                key = str(qa.get("apiKey", "")).strip()
                qa_enabled = bool(qa.get("enabled")) and (source_type == "magpie" or bool(key))
                auto_rows = any(
                    isinstance(q, dict) and str(q.get("provider") or "manual").lower() != "manual"
                    for q in (cfg.get("quotas") or [])
                )
                # 若 quotaApi 或套餐行直连启用，则视为启用
                enabled = enabled and (qa_enabled or auto_rows)
                if qa.get("intervalMin"):
                    try:
                        interval = max(60, int(qa["intervalMin"]) * 60)
                    except (ValueError, TypeError):
                        pass

            cur_sched = self._schedules.setdefault(s_id, {"last_run_ts": 0.0})
            # 源专属参数（如天气城市）变化时立即重拉，而不是等下个轮询周期
            fp = repr(sorted((k, v) for k, v in s_conf.items()
                             if k not in ("enabled", "intervalSec")))
            if "fp" in cur_sched and cur_sched["fp"] != fp:
                cur_sched["last_run_ts"] = 0.0
            cur_sched["fp"] = fp
            cur_sched["enabled"] = enabled
            cur_sched["interval_sec"] = interval
            cur_sched["kind"] = reg.info.kind

        # 立即检查并拉取已到期源（保证启动或配置启用时即刻刷新）
        self._on_tick()

    def _on_tick(self) -> None:
        if self._disposed:
            return
        now = time.time()
        due_ids = compute_due_sources(self._schedules, now)
        for s_id in due_ids:
            self.refresh(s_id)

    def _safe_emit(self, state: dict[str, Any]) -> None:
        if self._disposed:
            return
        try:
            self.updated.emit(state)
        except RuntimeError:
            pass

    def replay_states(self) -> None:
        """向监听者重放当前已缓存的所有数据源状态（常用于连接信号后的初始同步）。"""
        with self._lock:
            states = list(self._states.values())
        for state in states:
            self._safe_emit(state)

    def refresh(self, source_id: str | None = None) -> None:
        """触发指定源（或所有源）的数据拉取。"""
        target_ids = [source_id] if source_id else list(self._schedules.keys())
        for s_id in target_ids:
            reg = sources.get_source(s_id)
            if not reg:
                continue

            with self._lock:
                if s_id in self._busy_sources:
                    continue
                self._busy_sources.add(s_id)

            self._schedules.setdefault(s_id, {})["last_run_ts"] = time.time()

            if reg.info.kind == "local":
                # 本地高频源无网络 IO，直接同步运行（耗时 < 5ms）
                self._run_source_sync(reg)
            else:
                # 远程网络源放入工作线程执行，避免阻塞 UI
                threading.Thread(
                    target=self._run_source_async,
                    args=(reg,),
                    daemon=True,
                ).start()

    def _run_source_sync(self, reg: sources.SourceRegistration) -> None:
        s_id = reg.info.id
        try:
            tiles = reg.fetch_fn(self._cfg, timeout=3.0)
            self._handle_fetch_success(s_id, tiles)
        except Exception as e:
            _logger.info("local source [%s] fetch err: %s", s_id, str(e)[:160])
            self._handle_fetch_error(s_id, str(e))
        finally:
            with self._lock:
                self._busy_sources.discard(s_id)

    def _run_source_async(self, reg: sources.SourceRegistration) -> None:
        if self._disposed:
            return
        s_id = reg.info.id
        try:
            if s_id == "quota":
                # quota 源使用现有的全量聚合逻辑（保持向后兼容）
                self._fetch_quota_compat()
            else:
                tiles = reg.fetch_fn(self._cfg, timeout=8.0)
                if not self._disposed:
                    self._handle_fetch_success(s_id, tiles)
        except Exception as e:
            if not self._disposed:
                _logger.info("remote source [%s] fetch err: %s", s_id, str(e)[:160])
                self._handle_fetch_error(s_id, str(e))
        finally:
            with self._lock:
                self._busy_sources.discard(s_id)

    def _fetch_quota_compat(self) -> None:
        """执行 quota 源抓取，并组装向后兼容的 cards 与 row_updates 状态。"""
        from app.core.quota_api import (QuotaService, fetch_magpie_quotas,
                                  fetch_provider_quota, fetch_quota)

        qa = self._cfg.get("quotaApi") or {}
        source = str(qa.get("source", "glm"))
        key = str(qa.get("apiKey", "")).strip()
        qa_enabled = bool(qa.get("enabled")) and (source == "magpie" or bool(key))
        auto_rows = [
            (idx, dict(q))
            for idx, q in enumerate(self._cfg.get("quotas") or [])
            if isinstance(q, dict) and str(q.get("provider") or "manual").lower() != "manual"
        ]

        cards = []
        row_updates = {}
        errors = []

        if qa_enabled and not auto_rows:
            try:
                if source == "magpie":
                    magpie_url = str(qa.get("magpieUrl", "http://127.0.0.1:3425"))
                    magpie_provs = list(qa.get("magpieProviders") or [])
                    cards.extend(fetch_magpie_quotas(
                        magpie_url=magpie_url,
                        selected_ids=magpie_provs,
                    ))
                else:
                    base = str(qa.get("base", "bigmodel"))
                    team = QuotaService._team_of(qa)
                    info = fetch_quota(base, key, team=team)
                    cards.append({
                        "id": "glm",
                        "provider": "glm",
                        "name": "GLM",
                        "title": "GLM",
                        "plan": info.get("level", ""),
                        "level": info.get("level", ""),
                        "windows": info.get("windows", []),
                    })
            except Exception as e:
                errors.append(str(e))
                _logger.info("quota fetch primary fail: %s", str(e)[:160])

        for idx, row_item in auto_rows:
            try:
                res = fetch_provider_quota(row_item)
                row_updates[idx] = res
                if res.get("windows"):
                    cards.append(res)
            except Exception as e:
                errors.append(str(e))
                _logger.info("quota fetch row[%d] fail: %s", idx, str(e)[:160])

        if cards or row_updates:
            first_win = cards[0].get("windows", []) if cards else []
            first_lvl = cards[0].get("level", "") if cards else ""
            state = {
                "state": "ok",
                "ts": time.time(),
                "level": first_lvl,
                "windows": first_win,
                "cards": cards,
                "row_updates": row_updates,
                "source": "quota",
            }
            with self._lock:
                self._states["quota"] = state
            self._safe_emit(state)
        else:
            err_msg = "; ".join(errors) if errors else "未获取到有效套餐数据"
            with self._lock:
                prev = self._states.get("quota") or {}
                state = {
                    "state": "error",
                    "ts": time.time(),
                    "error": err_msg,
                    "source": "quota",
                }
                if prev.get("state") == "ok":
                    state["windows"] = prev.get("windows")
                    state["cards"] = prev.get("cards")
                    state["row_updates"] = prev.get("row_updates")
                    state["last_ok_ts"] = prev.get("ts")
                self._states["quota"] = state
            self._safe_emit(state)

    def _handle_fetch_success(self, source_id: str, tiles: list[dict[str, Any]]) -> None:
        state = {
            "source": source_id,
            "state": "ok",
            "ts": time.time(),
            "tiles": tiles,
        }
        with self._lock:
            self._states[source_id] = state
        self._safe_emit(state)

    def _handle_fetch_error(self, source_id: str, error_msg: str) -> None:
        with self._lock:
            prev = self._states.get(source_id) or {}
            state = {
                "source": source_id,
                "state": "error",
                "ts": time.time(),
                "error": error_msg,
                "tiles": prev.get("tiles", []),
                "last_ok_ts": prev.get("ts"),
            }
            self._states[source_id] = state
        self._safe_emit(state)
