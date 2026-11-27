"""app/sources/cursor_source.py — Cursor Fast Requests / Pro 剩余配额监控数据源

支持监控：
1. Cursor Pro / Business 的 Fast Requests 已用、剩余与上限；
2. 本月配额重置倒计时（下月 1 号重置）；
3. 本机 Cursor 会话凭据（WorkosCursorSessionToken）自动发现与 Cookie 鉴权；
4. 产出归一化 Tile: [cursor:fast, cursor:plan]。
"""

from __future__ import annotations

import calendar
import datetime
import json
import os
from pathlib import Path
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from app.core.tiles import fmt_num, make_tile, ratio_to_color

from . import SourceInfo, register


def discover_cursor_session() -> str | None:
    """自动从系统环境或 Cursor 本地全局存储发现会话 Token。"""
    # 1. 优先读取系统环境变量
    env_token = os.environ.get("CURSOR_SESSION_TOKEN", "").strip()
    if env_token:
        return env_token

    # 2. 检查 Cursor 本地配置路径
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    candidates = [
        Path(appdata) / "Cursor" / "User" / "globalStorage" / "storage.json",
        Path.home() / ".cursor" / "session.json",
    ]
    for p in candidates:
        try:
            if not p.exists():
                continue
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # 常见存储键名：cursorAuth/sessionToken 或 workosToken 等
                tok = (
                    data.get("cursorAuth/sessionToken")
                    or data.get("sessionToken")
                    or data.get("WorkosCursorSessionToken")
                    or data.get("token")
                )
                if tok and isinstance(tok, str) and tok.strip():
                    return tok.strip()
        except (OSError, ValueError):
            continue
    return None


def calculate_next_month_reset_ms(start_of_month_iso: str | None = None) -> int:
    """计算下一次月度配额重置的时间戳（毫秒）。"""
    now = datetime.datetime.now(datetime.timezone.utc)
    if start_of_month_iso:
        try:
            dt = datetime.datetime.fromisoformat(start_of_month_iso.replace("Z", "+00:00"))
            # 计算下月 1 号
            year = dt.year + (1 if dt.month == 12 else 0)
            month = 1 if dt.month == 12 else dt.month + 1
            reset_dt = datetime.datetime(year, month, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
            return int(reset_dt.timestamp() * 1000)
        except ValueError:
            pass

    # 兜底：当前月份顺延至下月 1 号 00:00:00 UTC
    year = now.year + (1 if now.month == 12 else 0)
    month = 1 if now.month == 12 else now.month + 1
    reset_dt = datetime.datetime(year, month, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
    return int(reset_dt.timestamp() * 1000)


def parse_cursor_usage(data: dict[str, Any]) -> dict[str, Any]:
    """纯函数解析 Cursor /api/usage 接口返回的用量 JSON。"""
    if not isinstance(data, dict):
        from app.core.quota_api import QuotaError
        raise QuotaError("Cursor 响应不是有效 JSON 对象")

    membership = str(data.get("membershipType") or data.get("plan") or "Pro").strip()
    plan_name = f"Cursor {membership.capitalize()}"

    # 提取 gpt4 或 primary 窗口
    gpt4_data = data.get("gpt4") if isinstance(data.get("gpt4"), dict) else data

    used = float(gpt4_data.get("numRequests", 0) or 0)
    limit = float(
        gpt4_data.get("maxRequestUsage")
        or gpt4_data.get("numRequestsTotal")
        or data.get("maxRequestUsage")
        or 500
    )
    slow_requests = float(gpt4_data.get("numSlowRequests", 0) or 0)

    remaining = max(0.0, limit - used) if limit > 0 else 0.0
    rem_pct = round(max(0.0, min(100.0, (remaining / limit) * 100.0)), 1) if limit > 0 else 0.0
    used_pct = round(max(0.0, min(100.0, 100.0 - rem_pct)), 1) if limit > 0 else 100.0

    reset_ms = calculate_next_month_reset_ms(data.get("startOfMonth"))

    windows = [
        {
            "kind": "requests",
            "name": "Fast Requests",
            "span_sec": 30 * 86400,
            "percent": used_pct,
            "used_percent": used_pct,
            "remaining_percent": rem_pct,
            "used": int(used),
            "remaining": int(remaining),
            "total": int(limit),
            "display": f"{int(remaining)}/{int(limit)} req",
            "reset_ms": reset_ms,
        }
    ]

    if slow_requests > 0:
        windows.append({
            "kind": "requests",
            "name": "Slow Requests",
            "span_sec": 30 * 86400,
            "percent": 100.0,
            "used_percent": 100.0,
            "remaining_percent": 100.0,
            "used": int(slow_requests),
            "remaining": None,
            "total": None,
            "display": f"{int(slow_requests)} req (慢速)",
            "reset_ms": reset_ms,
        })

    return {
        "id": "cursor",
        "provider": "cursor",
        "name": "Cursor",
        "plan": plan_name,
        "level": membership.capitalize(),
        "used": int(used),
        "limit": int(limit),
        "remaining": int(remaining),
        "unit": "req",
        "windows": windows,
    }


def fetch_cursor_usage(
    session_token: str = "",
    timeout: float = 6.0,
) -> dict[str, Any]:
    """通过 Cookie 鉴权查询 Cursor 官方 Fast Requests 配额。"""
    token = str(session_token or "").strip()
    if not token:
        discovered = discover_cursor_session()
        if discovered:
            token = discovered

    if not token:
        from app.core.quota_api import QuotaError
        raise QuotaError("未配置 Cursor Session Token (WorkosCursorSessionToken)")

    # 规范化 Cookie 格式
    cookie_val = (
        token if "WorkosCursorSessionToken=" in token
        else f"WorkosCursorSessionToken={token}"
    )

    req = urllib.request.Request(
        "https://www.cursor.com/api/usage",
        headers={
            "Cookie": cookie_val,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AnyBar/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            return parse_cursor_usage(data)
    except urllib.error.HTTPError as e:
        from app.core.quota_api import QuotaError
        if e.code in (401, 403):
            raise QuotaError("Cursor Token 已失效，请在设置中更新")
        raise QuotaError(f"Cursor 查询失败 HTTP {e.code}")
    except Exception as e:
        from app.core.quota_api import QuotaError
        raise QuotaError(f"Cursor 请求异常：{e}")


CURSOR_SOURCE_INFO = SourceInfo(
    id="cursor_quota",
    title="Cursor 算力配额",
    description="监控 Cursor Fast Requests、Pro 套餐剩余用量与月度重置倒计时",
    kind="remote",
    default_interval_sec=300,
    needs_credentials=True,
)


def fetch_cursor_tiles(cfg: dict[str, Any], timeout: float = 6.0) -> list[dict[str, Any]]:
    """作为通用 Source 时的顶层抓取入口，输出 Cursor 标称 Tile。"""
    src_cfg = (cfg.get("sources") or {}).get("cursor_quota") or {}
    tok = str(src_cfg.get("sessionToken") or src_cfg.get("apiKey") or "").strip()

    if not tok:
        for q in cfg.get("quotas") or []:
            if isinstance(q, dict) and str(q.get("provider") or "").lower() == "cursor":
                k = str(q.get("apiKey") or "").strip()
                if k:
                    tok = k
                    break

    try:
        usage = fetch_cursor_usage(session_token=tok, timeout=timeout)
    except Exception:
        # 降级回退
        return [
            make_tile(
                id="cursor:fast",
                source="cursor_quota",
                name="Cursor",
                ratio=1.0,
                center_text="Cursor",
                sub_text="Fast 待查",
                color="#007AFF",
                kind="ring",
                status="ok",
            )
        ]

    wins = usage.get("windows") or []
    primary = next((w for w in wins if w.get("name") == "Fast Requests"), wins[0] if wins else None)
    if not primary:
        return []

    rem_pct = float(primary.get("remaining_percent", 100.0))
    ratio = max(0.0, min(1.0, rem_pct / 100.0))
    pct_s = f"{int(round(rem_pct))}%"
    sub_s = str(primary.get("display") or f"{pct_s} 剩余")

    return [
        make_tile(
            id="cursor:fast",
            source="cursor_quota",
            name="Cursor Fast",
            ratio=ratio,
            center_text=pct_s,
            sub_text=sub_s,
            color=ratio_to_color(ratio),
            kind="ring",
            status="ok",
        )
    ]
