"""app/sources/quota_source.py — 算力额度与多渠道余额数据源

包装 app/quota_api 的各渠道 fetcher，向 app.sources 注册 "quota" 数据源，
并将 fetch_provider_quota 的 if/elif 链重构为表驱动分发。
"""

from __future__ import annotations

from typing import Any, Callable

from . import SourceInfo, register

# Provider 分发处理器注册表：prov_id -> handler_fn(item, key, base_url, name, timeout)
PROVIDER_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {}

# 渠道元数据列表：(provider_id, label, needs_key)
# 保持与 quota_api.PROVIDER_TYPES 格式与顺序严格一致
PROVIDER_SPECS: list[tuple[str, str]] = [
    ("magpie", "Magpie 同步"),
    ("claude", "Claude / Anthropic"),
    ("cursor", "Cursor 配额"),
    ("deepseek", "DeepSeek 余额"),
    ("openai", "OpenAI / ChatGPT"),
    ("codex", "ChatGPT Codex"),
    ("glm", "智谱 GLM"),
    ("kimi", "Kimi 余额"),
    ("openrouter", "OpenRouter"),
    ("newapi", "NewAPI 中转"),
    ("manual", "手动填写"),
]


def register_provider(prov_id: str | tuple[str, ...]) -> Callable[[Callable], Callable]:
    """Provider 分发处理器注册装饰器。"""
    def _decorator(fn: Callable) -> Callable:
        keys = (prov_id,) if isinstance(prov_id, str) else prov_id
        for k in keys:
            PROVIDER_HANDLERS[k.lower()] = fn
        return fn
    return _decorator


def dispatch_provider_quota(item: dict[str, Any], timeout: float = 8.0) -> dict[str, Any]:
    """通过分发表派发单个套餐的实时查询。"""
    from app.core.quota_api import QuotaError

    prov = str((item or {}).get("provider") or "manual").strip().lower()
    key = str((item or {}).get("apiKey") or "").strip()
    base_url = str((item or {}).get("baseUrl") or "").strip()
    name = str((item or {}).get("name") or prov).strip()

    handler = PROVIDER_HANDLERS.get(prov)
    if handler is None:
        raise QuotaError(f"不支持自动查询的类型：{prov}")

    res = handler(item=item, key=key, base_url=base_url, name=name, timeout=timeout)
    if name:
        res["name"] = name
    return res


# --- 渠道分发处理器实现（复用 quota_api 底层 fetcher） ---

@register_provider("deepseek")
def _handle_deepseek(item: dict, key: str, base_url: str, name: str, timeout: float) -> dict:
    from app.core.quota_api import fetch_deepseek_balance
    return fetch_deepseek_balance(key, timeout=timeout)


@register_provider(("kimi", "moonshot"))
def _handle_kimi(item: dict, key: str, base_url: str, name: str, timeout: float) -> dict:
    from app.core.quota_api import fetch_kimi_balance
    return fetch_kimi_balance(key, base_url=base_url, timeout=timeout)


@register_provider("openrouter")
def _handle_openrouter(item: dict, key: str, base_url: str, name: str, timeout: float) -> dict:
    from app.core.quota_api import fetch_openrouter_credits
    return fetch_openrouter_credits(key, timeout=timeout)


@register_provider("codex")
def _handle_codex(item: dict, key: str, base_url: str, name: str, timeout: float) -> dict:
    from app.core.quota_api import fetch_codex_usage, primary_window
    res = fetch_codex_usage(key, timeout=timeout)
    w = primary_window(res.get("windows"))
    if w is not None:
        rem_pct = w.get("remaining_percent")
        if rem_pct is None and w.get("percent") is not None:
            rem_pct = round(max(0.0, min(100.0, 100.0 - float(w["percent"]))), 1)
        res["used"] = rem_pct if rem_pct is not None else 100.0
        res["remaining"] = rem_pct if rem_pct is not None else 100.0
        res["limit"] = 100
        res["unit"] = "%"
    return res


@register_provider("magpie")
def _handle_magpie(item: dict, key: str, base_url: str, name: str, timeout: float) -> dict:
    from app.core.quota_api import QuotaError, fetch_magpie_quotas, primary_window
    cards = fetch_magpie_quotas(
        "http://127.0.0.1:3425",
        providers_filter=[key] if key else ([name] if name else None),
        timeout=timeout,
    )
    if not cards:
        raise QuotaError(f"Magpie 中未找到套餐：{key or name}")
    res = dict(cards[0])
    w = primary_window(res.get("windows"))
    if w is not None:
        rem_amt = w.get("remaining")
        rem_pct = w.get("remaining_percent")
        if rem_pct is None and w.get("percent") is not None:
            rem_pct = round(max(0.0, min(100.0, 100.0 - float(w["percent"]))), 1)
        if rem_amt is not None and w.get("total") is not None and w["total"] > 100:
            res["used"] = rem_amt
            res["remaining"] = rem_amt
            res["limit"] = w["total"]
            res["unit"] = ""
        elif rem_pct is not None:
            res["used"] = rem_pct
            res["remaining"] = rem_pct
            res["limit"] = 100
            res["unit"] = "%"
    return res


@register_provider("glm")
def _handle_glm(item: dict, key: str, base_url: str, name: str, timeout: float) -> dict:
    from app.core.quota_api import discover_team_context, fetch_quota, primary_window
    site = base_url if base_url in ("bigmodel", "zai") else "bigmodel"
    team = discover_team_context(base=site)
    info = fetch_quota(site, key, team=team, timeout=timeout)
    res = {
        "id": f"glm/{name}",
        "provider": "glm",
        "name": name or "GLM",
        "title": name or "GLM",
        "plan": info.get("level", ""),
        "level": info.get("level", ""),
        "windows": info.get("windows", []),
    }
    w = primary_window(info.get("windows"))
    if w is not None:
        if w.get("used") is not None and w.get("total") is not None:
            res["used"] = w["used"]
            res["limit"] = w["total"]
        elif w.get("percent") is not None:
            res["used"] = round(float(w["percent"]), 1)
            res["limit"] = 100
            res["unit"] = "%"
    return res


@register_provider("newapi")
def _handle_newapi(item: dict, key: str, base_url: str, name: str, timeout: float) -> dict:
    from app.core.quota_api import fetch_newapi_usage
    return fetch_newapi_usage(key, base_url=base_url, timeout=timeout)


@register_provider(("claude", "anthropic"))
def _handle_claude(item: dict, key: str, base_url: str, name: str, timeout: float) -> dict:
    from app.core.sources.claude_source import fetch_claude_usage
    res = fetch_claude_usage(api_key=key, base_url=base_url, timeout=timeout)
    if name:
        res["name"] = name
    return res


@register_provider("cursor")
def _handle_cursor(item: dict, key: str, base_url: str, name: str, timeout: float) -> dict:
    from app.core.sources.cursor_source import fetch_cursor_usage
    res = fetch_cursor_usage(session_token=key, timeout=timeout)
    if name:
        res["name"] = name
    return res


@register_provider("openai")
def _handle_openai(item: dict, key: str, base_url: str, name: str, timeout: float) -> dict:
    from app.core.sources.deepseek_source import fetch_openai_usage
    res = fetch_openai_usage(api_key=key, base_url=base_url, timeout=timeout)
    if name:
        res["name"] = name
    return res


# 向全局源注册表登记 "quota" 数据源
@register(
    SourceInfo(
        id="quota",
        title="算力与模型额度",
        kind="remote",
        default_interval_sec=600,
        min_interval_sec=60,
        needs_credentials=True,
    )
)
def fetch_quota_tiles(cfg: dict[str, Any], timeout: float = 8.0) -> list[dict[str, Any]]:
    """作为通用 Source 时的顶层抓取入口，返回归一化的 Tile 列表。"""
    from app.core.tiles import tiles_from_quota_state
    # 从配置的套餐列表中尝试更新，由调度层调用
    return tiles_from_quota_state(None, cfg)
