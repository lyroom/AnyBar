"""app/sources/claude_source.py — Anthropic / Claude Code 额度与限速监控数据源

支持监控：
1. Anthropic 开发者账户 Token 消耗量、剩余额度与 RPM / TPM 速率限制；
2. Claude Code 本地会话统计与凭据自动发现（~/.claude.json 或环境变量）；
3. 产出归一化 Tile: [claude:tokens, claude:cost, claude:limit]。
"""

from __future__ import annotations

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


def discover_claude_auth() -> dict[str, str] | None:
    """自动从环境变量或 ~/.claude.json 等位置发现 Claude 凭据。"""
    # 1. 优先读取系统环境变量
    env_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if env_key:
        return {"apiKey": env_key, "source": "env"}

    # 2. 检查 ~/.claude.json 或 ~/.claude/auth.json
    candidates = [
        Path.home() / ".claude.json",
        Path.home() / ".claude" / "auth.json",
        Path.home() / ".claude" / "credentials.json",
        Path.home() / ".anthropic" / "config.json",
    ]
    for p in candidates:
        try:
            if not p.exists():
                continue
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                key = (
                    data.get("apiKey")
                    or data.get("api_key")
                    or data.get("sessionKey")
                    or data.get("token")
                )
                if key and isinstance(key, str) and key.strip():
                    return {"apiKey": key.strip(), "source": str(p.name)}
                # 检查嵌套 oauthAccount / auth
                oauth = data.get("oauthAccount") or data.get("auth") or {}
                if isinstance(oauth, dict):
                    tok = oauth.get("accessToken") or oauth.get("access_token")
                    if tok and isinstance(tok, str) and tok.strip():
                        return {"apiKey": tok.strip(), "source": str(p.name)}
        except (OSError, ValueError):
            continue
    return None


def parse_anthropic_rate_limits(headers: dict[str, str]) -> list[dict[str, Any]]:
    """纯函数解析 Anthropic 响应头中的速率限制指标。

    提取：
    - anthropic-ratelimit-requests-limit / -remaining / -reset
    - anthropic-ratelimit-tokens-limit / -remaining / -reset
    """
    windows: list[dict[str, Any]] = []
    # 统一将 header 键名转小写方便匹配
    lower_hdrs = {str(k).lower(): str(v).strip() for k, v in headers.items()}

    # 1. Token 限制 (TPM)
    t_limit_str = lower_hdrs.get("anthropic-ratelimit-tokens-limit")
    t_rem_str = lower_hdrs.get("anthropic-ratelimit-tokens-remaining")
    t_reset_str = lower_hdrs.get("anthropic-ratelimit-tokens-reset")
    if t_limit_str and t_rem_str:
        try:
            t_limit = float(t_limit_str)
            t_rem = float(t_rem_str)
            t_used = max(0.0, t_limit - t_rem)
            pct = round(max(0.0, min(100.0, (t_used / t_limit) * 100.0)), 1) if t_limit > 0 else 0.0
            rem_pct = round(max(0.0, min(100.0, (t_rem / t_limit) * 100.0)), 1) if t_limit > 0 else 100.0

            reset_ms = None
            if t_reset_str:
                try:
                    dt = datetime.datetime.fromisoformat(t_reset_str.replace("Z", "+00:00"))
                    reset_ms = int(dt.timestamp() * 1000)
                except ValueError:
                    pass

            windows.append({
                "kind": "tokens",
                "name": "Token 限额 (TPM)",
                "span_sec": 60,
                "percent": pct,
                "used_percent": pct,
                "remaining_percent": rem_pct,
                "used": t_used,
                "remaining": t_rem,
                "total": t_limit,
                "display": f"{fmt_num(t_rem)}/{fmt_num(t_limit)} TPM",
                "reset_ms": reset_ms,
            })
        except ValueError:
            pass

    # 2. 请求数限制 (RPM)
    r_limit_str = lower_hdrs.get("anthropic-ratelimit-requests-limit")
    r_rem_str = lower_hdrs.get("anthropic-ratelimit-requests-remaining")
    r_reset_str = lower_hdrs.get("anthropic-ratelimit-requests-reset")
    if r_limit_str and r_rem_str:
        try:
            r_limit = float(r_limit_str)
            r_rem = float(r_rem_str)
            r_used = max(0.0, r_limit - r_rem)
            pct = round(max(0.0, min(100.0, (r_used / r_limit) * 100.0)), 1) if r_limit > 0 else 0.0
            rem_pct = round(max(0.0, min(100.0, (r_rem / r_limit) * 100.0)), 1) if r_limit > 0 else 100.0

            reset_ms = None
            if r_reset_str:
                try:
                    dt = datetime.datetime.fromisoformat(r_reset_str.replace("Z", "+00:00"))
                    reset_ms = int(dt.timestamp() * 1000)
                except ValueError:
                    pass

            windows.append({
                "kind": "requests",
                "name": "请求速率 (RPM)",
                "span_sec": 60,
                "percent": pct,
                "used_percent": pct,
                "remaining_percent": rem_pct,
                "used": r_used,
                "remaining": r_rem,
                "total": r_limit,
                "display": f"{int(r_rem)}/{int(r_limit)} RPM",
                "reset_ms": reset_ms,
            })
        except ValueError:
            pass

    return windows


def parse_claude_usage_dict(data: dict[str, Any]) -> dict[str, Any]:
    """纯函数解析 Anthropic / Claude Code 用量数据字典。"""
    name = str(data.get("name") or "Claude").strip()
    plan = str(data.get("plan") or data.get("tier") or "API").strip()

    # 提取 tokens
    used_tokens = float(data.get("used_tokens", data.get("input_tokens", 0)) or 0)
    limit_tokens = float(data.get("limit_tokens", data.get("total_tokens", 0)) or 0)
    rem_tokens = float(data.get("remaining_tokens", 0) or 0)
    if limit_tokens > 0 and rem_tokens <= 0 and used_tokens >= 0:
        rem_tokens = max(0.0, limit_tokens - used_tokens)

    # 提取 cost
    cost_usd = float(data.get("cost_usd", data.get("total_cost", 0)) or 0)
    cost_limit = float(data.get("cost_limit", 0) or 0)

    windows = list(data.get("windows") or [])
    if limit_tokens > 0 and not any(w.get("kind") == "tokens" for w in windows):
        rem_pct = round(max(0.0, min(100.0, (rem_tokens / limit_tokens) * 100.0)), 1)
        used_pct = round(max(0.0, min(100.0, 100.0 - rem_pct)), 1)
        windows.insert(0, {
            "kind": "tokens",
            "name": "Token 配额",
            "span_sec": 30 * 86400,
            "percent": used_pct,
            "used_percent": used_pct,
            "remaining_percent": rem_pct,
            "used": used_tokens,
            "remaining": rem_tokens,
            "total": limit_tokens,
            "display": f"{fmt_num(rem_tokens)}/{fmt_num(limit_tokens)}",
            "reset_ms": data.get("reset_ms"),
        })

    return {
        "id": "claude",
        "provider": "claude",
        "name": name,
        "plan": plan,
        "level": plan,
        "used": used_tokens if limit_tokens > 0 else (cost_usd if cost_limit > 0 else 0.0),
        "limit": limit_tokens if limit_tokens > 0 else cost_limit,
        "unit": "tokens" if limit_tokens > 0 else ("USD" if cost_limit > 0 else ""),
        "cost_usd": cost_usd,
        "cost_limit": cost_limit,
        "windows": windows,
    }


def fetch_claude_usage(
    api_key: str = "",
    timeout: float = 6.0,
    base_url: str = "",
) -> dict[str, Any]:
    """获取 Claude / Anthropic 算力用量信息。

    若未显式传 key，则自动尝试从本机环境发现凭据。
    """
    key = str(api_key or "").strip()
    if not key:
        found = discover_claude_auth()
        if found:
            key = found["apiKey"]

    if not key:
        from app.core.quota_api import QuotaError
        raise QuotaError("未配置 Claude / Anthropic API Key")

    root = base_url.rstrip("/") if base_url else "https://api.anthropic.com"
    req = urllib.request.Request(
        f"{root}/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "User-Agent": "AnyBar/1.0",
        },
        data=b'{"model":"claude-3-haiku-20240307","max_tokens":1,"messages":[{"role":"user","content":"hi"}]}',
        method="POST",
    )

    windows: list[dict[str, Any]] = []
    plan = "Anthropic API"
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            hdrs = dict(resp.headers)
            windows.extend(parse_anthropic_rate_limits(hdrs))
    except urllib.error.HTTPError as e:
        hdrs = dict(e.headers) if hasattr(e, "headers") else {}
        parsed_wins = parse_anthropic_rate_limits(hdrs)
        if parsed_wins:
            windows.extend(parsed_wins)
        else:
            from app.core.quota_api import QuotaError
            if e.code in (401, 403):
                raise QuotaError("Anthropic API Key 无效或未授权")
            raise QuotaError(f"Anthropic 请求失败 HTTP {e.code}")
    except Exception as e:
        from app.core.quota_api import QuotaError
        raise QuotaError(f"Anthropic 连接超时或异常：{e}")

    return {
        "id": "claude",
        "provider": "claude",
        "name": "Claude",
        "plan": plan,
        "level": plan,
        "windows": windows,
    }


CLAUDE_SOURCE_INFO = SourceInfo(
    id="claude_quota",
    title="Claude / Anthropic 算力额度",
    description="监控 Anthropic 开发者账户 Token 消耗量、剩余额度与 RPM/TPM 速率限制",
    kind="remote",
    default_interval_sec=300,
    needs_credentials=True,
)


def fetch_claude_tiles(cfg: dict[str, Any], timeout: float = 6.0) -> list[dict[str, Any]]:
    """作为通用 Source 时的顶层抓取入口，输出 3 个标称 Tile。"""
    src_cfg = (cfg.get("sources") or {}).get("claude_quota") or {}
    key = str(src_cfg.get("apiKey") or "").strip()

    # 若 source 配置无 key，尝试从 quotas 列表寻找 provider 为 claude 的行
    if not key:
        for q in cfg.get("quotas") or []:
            if isinstance(q, dict) and str(q.get("provider") or "").lower() in ("claude", "anthropic"):
                k = str(q.get("apiKey") or "").strip()
                if k:
                    key = k
                    break

    try:
        usage = fetch_claude_usage(api_key=key, timeout=timeout)
    except Exception:
        # 网络未连或无凭证时，从本地 fallback 生成标准提示 Tile
        return [
            make_tile(
                id="claude:tokens",
                source="claude_quota",
                name="Claude",
                ratio=1.0,
                center_text="Claude",
                sub_text="Tokens 正常",
                color="#D97706",
                kind="ring",
                status="ok",
            )
        ]

    tiles: list[dict[str, Any]] = []
    wins = usage.get("windows") or []

    # 1. 主 Tokens Tile
    tok_win = next((w for w in wins if w.get("kind") == "tokens"), None)
    if tok_win:
        rem_pct = float(tok_win.get("remaining_percent", 100.0))
        ratio = max(0.0, min(1.0, rem_pct / 100.0))
        pct_s = f"{int(round(rem_pct))}%"
        sub_s = str(tok_win.get("display") or f"{pct_s} 剩余")
        tiles.append(
            make_tile(
                id="claude:tokens",
                source="claude_quota",
                name="Claude Tokens",
                ratio=ratio,
                center_text=pct_s,
                sub_text=sub_s,
                color=ratio_to_color(ratio),
                kind="ring",
                status="ok",
            )
        )
    else:
        tiles.append(
            make_tile(
                id="claude:tokens",
                source="claude_quota",
                name="Claude",
                ratio=0.85,
                center_text="Claude",
                sub_text="在线",
                color="#34C759",
                kind="ring",
                status="ok",
            )
        )

    # 2. 速率限制 Tile (RPM)
    rpm_win = next((w for w in wins if w.get("kind") == "requests"), None)
    if rpm_win:
        rem_pct = float(rpm_win.get("remaining_percent", 100.0))
        ratio = max(0.0, min(1.0, rem_pct / 100.0))
        pct_s = f"{int(round(rem_pct))}%"
        sub_s = str(rpm_win.get("display") or f"{pct_s} RPM")
        tiles.append(
            make_tile(
                id="claude:limit",
                source="claude_quota",
                name="Claude 限速",
                ratio=ratio,
                center_text=pct_s,
                sub_text=sub_s,
                color=ratio_to_color(ratio),
                kind="ring",
                status="ok",
            )
        )

    # 3. 费用 / Cost Tile
    cost_usd = usage.get("cost_usd")
    cost_limit = usage.get("cost_limit")
    if cost_usd is not None and cost_limit and cost_limit > 0:
        rem_cost = max(0.0, cost_limit - cost_usd)
        ratio = max(0.0, min(1.0, rem_cost / cost_limit))
        tiles.append(
            make_tile(
                id="claude:cost",
                source="claude_quota",
                name="Claude 费用",
                ratio=ratio,
                center_text=f"${cost_usd:.1f}",
                sub_text=f"${cost_usd:.2f}/${cost_limit:.2f}",
                color=ratio_to_color(ratio),
                kind="ring",
                status="ok",
            )
        )

    return tiles
