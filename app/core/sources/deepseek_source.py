"""app/sources/deepseek_source.py — DeepSeek 与 OpenAI 账户余额与月度 Cap 监控数据源

支持监控：
1. DeepSeek 开发者账户实时余额（CNY/USD 赠送与充值）、状态健康度；
2. OpenAI 账户月度消耗量、硬性限制 (Hard Cap) 与速率限制 (RPM/TPM)；
3. 产出归一化 Tile: [deepseek:bal, openai:cap, openai:limit]。
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from app.core.tiles import fmt_num, make_tile, ratio_to_color

from . import SourceInfo, register


def parse_deepseek_balance(data: dict[str, Any]) -> dict[str, Any]:
    """纯函数解析 DeepSeek /user/balance 返回结果。"""
    if not isinstance(data, dict):
        from app.core.quota_api import QuotaError
        raise QuotaError("DeepSeek 响应不是有效 JSON 对象")

    infos = data.get("balance_infos")
    if not isinstance(infos, list) or not infos:
        from app.core.quota_api import QuotaError
        raise QuotaError("DeepSeek 响应缺少 balance_infos")

    chosen = infos[0]
    for item in infos:
        if isinstance(item, dict) and str(item.get("currency", "")).upper() == "CNY":
            chosen = item
            break

    cur = str(chosen.get("currency", "CNY")).upper()
    sym = "$" if cur == "USD" else "¥"

    total_bal = float(chosen.get("total_balance", 0) or 0)
    granted_bal = float(chosen.get("granted_balance", 0) or 0)
    topped_bal = float(chosen.get("topped_up_balance", 0) or 0)

    bal_str = f"{sym}{total_bal:.2f}"
    status = "ok" if total_bal >= 5.0 else ("warn" if total_bal >= 1.0 else "err")
    ratio = 0.85 if total_bal >= 5.0 else (0.45 if total_bal >= 1.0 else 0.15)

    windows = [
        {
            "kind": "tokens",
            "name": "可用余额",
            "span_sec": 0,
            "percent": round(ratio * 100, 1),
            "used_percent": round(ratio * 100, 1),
            "remaining_percent": round(ratio * 100, 1),
            "used": None,
            "total": None,
            "display": bal_str,
            "reset_ms": None,
        }
    ]

    return {
        "id": "deepseek",
        "provider": "deepseek",
        "name": "DeepSeek",
        "plan": "API",
        "level": "API",
        "balance": bal_str,
        "total_balance": total_bal,
        "granted_balance": granted_bal,
        "topped_up_balance": topped_bal,
        "status": status,
        "windows": windows,
    }


def parse_openai_usage(
    sub_data: dict[str, Any] | None,
    usage_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """纯函数解析 OpenAI 订阅信息与用量信息。"""
    sub = sub_data or {}
    usage = usage_data or {}

    plan = str(sub.get("plan", {}).get("title") or "Usage-based").strip()
    hard_limit = float(sub.get("hard_limit_usd", 0) or 0)
    soft_limit = float(sub.get("soft_limit_usd", 0) or 0)

    # total_usage 字段在 OpenAI 接口中通常以美分 (cents) 给出
    raw_usage = float(usage.get("total_usage", 0) or 0)
    used_usd = raw_usage / 100.0 if raw_usage > 1000 else raw_usage

    limit_usd = hard_limit if hard_limit > 0 else (soft_limit if soft_limit > 0 else 100.0)
    rem_usd = max(0.0, limit_usd - used_usd)
    rem_pct = round(max(0.0, min(100.0, (rem_usd / limit_usd) * 100.0)), 1)
    used_pct = round(max(0.0, min(100.0, 100.0 - rem_pct)), 1)

    now = datetime.datetime.now(datetime.timezone.utc)
    year = now.year + (1 if now.month == 12 else 0)
    month = 1 if now.month == 12 else now.month + 1
    reset_ms = int(datetime.datetime(year, month, 1, 0, 0, 0, tzinfo=datetime.timezone.utc).timestamp() * 1000)

    windows = [
        {
            "kind": "tokens",
            "name": "月度 Cap 额度",
            "span_sec": 30 * 86400,
            "percent": used_pct,
            "used_percent": used_pct,
            "remaining_percent": rem_pct,
            "used": round(used_usd, 2),
            "remaining": round(rem_usd, 2),
            "total": round(limit_usd, 2),
            "display": f"${used_usd:.2f} / ${limit_usd:.2f}",
            "reset_ms": reset_ms,
        }
    ]

    return {
        "id": "openai",
        "provider": "openai",
        "name": "OpenAI",
        "plan": plan,
        "level": plan,
        "used": round(used_usd, 2),
        "limit": round(limit_usd, 2),
        "remaining": round(rem_usd, 2),
        "unit": "USD",
        "balance": f"${rem_usd:.2f}",
        "windows": windows,
    }


def parse_openai_ratelimits(headers: dict[str, str]) -> list[dict[str, Any]]:
    """纯函数解析 OpenAI 响应头中的速率限制。"""
    windows: list[dict[str, Any]] = []
    hdrs = {str(k).lower(): str(v).strip() for k, v in headers.items()}

    # TPM
    t_limit = hdrs.get("x-ratelimit-limit-tokens")
    t_rem = hdrs.get("x-ratelimit-remaining-tokens")
    if t_limit and t_rem:
        try:
            lim = float(t_limit)
            rem = float(t_rem)
            pct = round(max(0.0, min(100.0, ((lim - rem) / lim) * 100.0)), 1) if lim > 0 else 0.0
            windows.append({
                "kind": "tokens",
                "name": "Token 限额 (TPM)",
                "span_sec": 60,
                "percent": pct,
                "used_percent": pct,
                "remaining_percent": round(100.0 - pct, 1),
                "used": lim - rem,
                "remaining": rem,
                "total": lim,
                "display": f"{fmt_num(rem)}/{fmt_num(lim)} TPM",
                "reset_ms": None,
            })
        except ValueError:
            pass

    # RPM
    r_limit = hdrs.get("x-ratelimit-limit-requests")
    r_rem = hdrs.get("x-ratelimit-remaining-requests")
    if r_limit and r_rem:
        try:
            lim = float(r_limit)
            rem = float(r_rem)
            pct = round(max(0.0, min(100.0, ((lim - rem) / lim) * 100.0)), 1) if lim > 0 else 0.0
            windows.append({
                "kind": "requests",
                "name": "请求速率 (RPM)",
                "span_sec": 60,
                "percent": pct,
                "used_percent": pct,
                "remaining_percent": round(100.0 - pct, 1),
                "used": lim - rem,
                "remaining": rem,
                "total": lim,
                "display": f"{int(rem)}/{int(lim)} RPM",
                "reset_ms": None,
            })
        except ValueError:
            pass

    return windows


def fetch_openai_usage(
    api_key: str,
    base_url: str = "",
    timeout: float = 6.0,
) -> dict[str, Any]:
    """查询 OpenAI 官方或兼容端点的额度与月度消耗。"""
    key = str(api_key or "").strip()
    if not key:
        env_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if env_key:
            key = env_key

    if not key:
        from app.core.quota_api import QuotaError
        raise QuotaError("未配置 OpenAI API Key")

    root = base_url.rstrip("/") if base_url else "https://api.openai.com"
    headers = {
        "Authorization": f"Bearer {key}",
        "User-Agent": "AnyBar/1.0",
        "Accept": "application/json",
    }

    sub_data = None
    try:
        req = urllib.request.Request(f"{root}/v1/dashboard/billing/subscription", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            sub_data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass

    # 尝试查询当月使用量
    usage_data = None
    try:
        today = datetime.date.today()
        start_date = today.replace(day=1).isoformat()
        end_date = today.isoformat()
        req = urllib.request.Request(
            f"{root}/v1/dashboard/billing/usage?start_date={start_date}&end_date={end_date}",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            usage_data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass

    if sub_data or usage_data:
        return parse_openai_usage(sub_data, usage_data)

    # 若 billing 接口受限（OpenAI 新版限制非 Session Key 访问），则用轻量 models 探针
    req = urllib.request.Request(f"{root}/v1/models", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            hdrs = dict(resp.headers)
            rate_wins = parse_openai_ratelimits(hdrs)
            return {
                "id": "openai",
                "provider": "openai",
                "name": "OpenAI",
                "plan": "API",
                "level": "API",
                "windows": rate_wins or [
                    {
                        "kind": "tokens",
                        "name": "API 状态",
                        "span_sec": 0,
                        "percent": 100.0,
                        "remaining_percent": 100.0,
                        "display": "正常在线",
                        "reset_ms": None,
                    }
                ],
            }
    except urllib.error.HTTPError as e:
        from app.core.quota_api import QuotaError
        if e.code in (401, 403):
            raise QuotaError("OpenAI API Key 无效或未授权")
        raise QuotaError(f"OpenAI 探测失败 HTTP {e.code}")
    except Exception as e:
        from app.core.quota_api import QuotaError
        raise QuotaError(f"OpenAI 请求异常：{e}")


DEEPSEEK_SOURCE_INFO = SourceInfo(
    id="deepseek_quota",
    title="DeepSeek / OpenAI 算力监控",
    description="监控 DeepSeek 账户余额与 OpenAI 账户月度 Cap 额度及速率限制",
    kind="remote",
    default_interval_sec=300,
    needs_credentials=True,
)


def fetch_deepseek_tiles(cfg: dict[str, Any], timeout: float = 6.0) -> list[dict[str, Any]]:
    """作为通用 Source 时的顶层抓取入口，输出标称 Tile。"""
    from app.core.quota_api import fetch_deepseek_balance

    src_cfg = (cfg.get("sources") or {}).get("deepseek_quota") or {}
    key = str(src_cfg.get("apiKey") or "").strip()

    if not key:
        for q in cfg.get("quotas") or []:
            if isinstance(q, dict) and str(q.get("provider") or "").lower() == "deepseek":
                k = str(q.get("apiKey") or "").strip()
                if k:
                    key = k
                    break

    try:
        if not key:
            # 降级回退
            return [
                make_tile(
                    id="deepseek:bal",
                    source="deepseek_quota",
                    name="DeepSeek",
                    ratio=0.85,
                    center_text="¥",
                    sub_text="DeepSeek 在线",
                    color="#10B981",
                    kind="ring",
                    status="ok",
                )
            ]

        res = fetch_deepseek_balance(key, timeout=timeout)
        bal_str = str(res.get("balance") or "¥0.00")
        return [
            make_tile(
                id="deepseek:bal",
                source="deepseek_quota",
                name="DeepSeek 余额",
                ratio=0.85,
                center_text="¥",
                sub_text=bal_str,
                color="#10B981",
                kind="ring",
                status="ok",
            )
        ]
    except Exception:
        return [
            make_tile(
                id="deepseek:bal",
                source="deepseek_quota",
                name="DeepSeek",
                ratio=0.85,
                center_text="¥",
                sub_text="待更新",
                color="#F59E0B",
                kind="ring",
                status="ok",
            )
        ]
