"""GLM Coding Plan 余额自动查询。

接口与 zai-org/zai-coding-plugins（官方 Claude Code 插件）同源：
GET {站点根}/api/monitor/usage/quota/limit，请求头 Authorization 直接携带
API Key（401/403 时回退一次 Bearer 前缀）。响应为 {code, msg, data} 包装，
code 为 0/200 视为成功；data.level 是套餐档位，data.limits[] 内：
- TOKENS_LIMIT：模型 token 用量窗口（GLM 套餐为 5 小时窗 + 每周窗两个条目）
- TIME_LIMIT：MCP 工具月度调用量（不阻断模型，仅展示）
百分比优先用 usage/remaining 推算，其次 currentValue/usage，最后 percentage。

团队套餐（与 magpie 社区插件 teamUsage 同路）：同一个接口必须同时加
?type=2 与 Bigmodel-Organization / Bigmodel-Project 两个请求头才返回团队
额度；裸 key（无论个人还是团队的 key）只返回个人套餐。团队 org/project ID
可从 ZCode 应用凭据（~/.zcode/v2/credentials.json）的键名明文中自动发现，
无需用户手填（值是加密的，读不了也不需要读）。

纯解析函数不依赖 Qt，可在无 GUI 环境下单测；QuotaService 用守护线程发请求，
结果经 Signal 跨线程投递回主线程（自动队列连接），绝不阻塞 UI。
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from . import config as config_mod
from .logger import get_logger

QUOTA_LIMIT_PATH = "/api/monitor/usage/quota/limit"
# 允许的站点域名后缀（官方插件同样只认这两个域）
_ALLOWED_DOMAINS = ("bigmodel.cn", "z.ai")
# limits[].unit 枚举 → 单位秒数（与 magpie 社区插件逆向一致）：
# 1=分钟 3=小时 4=天 5=30天(月) 6=7天(周)；number 为数量，团队版 5h 窗不带 number
_UNIT_SECONDS = {1: 60, 3: 3600, 4: 86400, 5: 30 * 86400, 6: 7 * 86400}

_q_logger = get_logger("anybar.quota", "quota.log", env_var="TOUCHBAR_QUOTA_LOG")


class QuotaError(Exception):
    """查询失败（网络 / 鉴权 / 业务码异常），message 面向用户可直接展示。"""


def _num(v):
    """把接口里的数字字段统一成 float，非法/缺失返回 None。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def site_root(base: str) -> str:
    """站点键或完整 URL → API 根地址；不认识的站点抛 QuotaError。"""
    sites = config_mod.QUOTA_SITES
    key = str(base or "").strip()
    if key in sites:
        return sites[key]
    if key.startswith("http://") or key.startswith("https://"):
        from urllib.parse import urlparse
        host = urlparse(key).hostname or ""
        if any(host == d or host.endswith("." + d) for d in _ALLOWED_DOMAINS):
            return f"{urlparse(key).scheme}://{host}"
    raise QuotaError(f"未知站点：{base!r}（支持 open.bigmodel.cn / api.z.ai）")


def parse_envelope(env) -> dict:
    """校验 {code, msg, data} 包装，返回 data 字典；业务失败抛 QuotaError。"""
    if not isinstance(env, dict):
        raise QuotaError("响应不是 JSON 对象")
    code = env.get("code")
    if code is not None and str(code) not in ("0", "200"):
        raise QuotaError(f"接口错误 code={code}：{env.get('msg') or '未知错误'}")
    data = env.get("data")
    if not isinstance(data, dict):
        data = {}
    return data


def window_span_sec(item: dict) -> int:
    """按 unit×number 推算窗口时长（秒），推不出返回 0。"""
    unit = int(_num(item.get("unit")) or 0)
    n = int(_num(item.get("number")) or 0)
    if unit == 3 and n <= 0:
        n = 5  # 团队版 5 小时窗不带 count
    n = max(n, 1)
    return _UNIT_SECONDS.get(unit, 0) * n


def window_name(span_sec: int) -> str:
    """窗口时长 → 展示名（勿按返回顺序命名，接口顺序不保证 5h 在前）。"""
    if span_sec <= 0:
        return "额度窗口"
    if span_sec < 86400:
        return f"{span_sec // 3600} 小时窗口"
    if span_sec == 7 * 86400:
        return "每周窗口"
    if span_sec >= 28 * 86400:
        return "每月窗口"
    return f"{span_sec // 86400} 天窗口"


def parse_quota_payload(payload) -> dict:
    """解析 quota/limit 的 data 为规整结构（纯函数）。

    返回 {"level": "pro", "windows": [
        {"kind": "tokens"|"mcp", "name": "5 小时窗口", "span_sec": 18000,
         "percent": 42.5, "used": 8.5, "total": 20.0, "reset_ms": 1729...}]}；
    percent/used/total/reset_ms 任一缺失为 None。
    """
    data = payload if isinstance(payload, dict) else {}
    level = str(data.get("level") or "").strip()
    windows = []
    limits = data.get("limits")
    for item in limits if isinstance(limits, list) else []:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").upper() == "TIME_LIMIT":
            kind = "mcp"
            name = "MCP · 本月"
        else:
            kind = "tokens"
            name = window_name(window_span_sec(item))
        w = {"kind": kind, "name": name, "span_sec": window_span_sec(item),
             "percent": None, "used": None, "total": None, "reset_ms": None}
        usage = _num(item.get("usage"))
        remaining = _num(item.get("remaining"))
        current = _num(item.get("currentValue"))
        pct = _num(item.get("percentage"))
        if usage is not None and usage > 0 and remaining is not None:
            used = max(0.0, usage - remaining)
            w["used"], w["total"] = used, usage
            w["percent"] = round(used / usage * 100.0, 1)
        elif usage is not None and usage > 0 and current is not None:
            w["used"], w["total"] = current, usage
            w["percent"] = round(min(100.0, current / usage * 100.0), 1)
        elif pct is not None:
            w["percent"] = round(max(0.0, min(100.0, pct)), 1)
        reset = _num(item.get("nextResetTime"))
        if reset is not None and reset > 1e12:  # 毫秒级 epoch
            w["reset_ms"] = int(reset)
        if (w["percent"] is None and w["used"] is None
                and w["total"] is None and w["reset_ms"] is None):
            continue  # 完全无数据的条目（如空对象）不生成窗口
        windows.append(w)
    return {"level": level, "windows": windows}


def primary_window(windows):
    """取主展示窗口：tokens 类中时长最短者（GLM 套餐即 5 小时窗）。

    时长未知(span_sec=0)的排在已知时长之后；无 tokens 窗口返回 None。
    """
    cands = [w for w in (windows or [])
             if isinstance(w, dict) and w.get("kind") == "tokens"
             and w.get("percent") is not None]
    if not cands:
        return None

    def _rank(w):
        s = w.get("span_sec") or 0
        return s if s > 0 else 1 << 30

    return min(cands, key=_rank)


def _extract_msg(body: str) -> str:
    try:
        env = json.loads(body)
        if isinstance(env, dict) and env.get("msg"):
            return str(env["msg"])
    except (ValueError, TypeError):
        pass
    return (body or "").strip()[:120]


def quota_limit_url(root: str, team=None) -> str:
    """余额接口完整 URL；team 上下文（{"org","project"}）时加 ?type=2。"""
    url = root + QUOTA_LIMIT_PATH
    if team:
        url += "?type=2"
    return url


def team_headers(team) -> dict:
    """团队上下文 → Bigmodel-Organization/Bigmodel-Project 请求头。"""
    org = str((team or {}).get("org") or "").strip()
    proj = str((team or {}).get("project") or "").strip()
    return {"Bigmodel-Organization": org, "Bigmodel-Project": proj}


def _http_get_json(url: str, auth: str, timeout: float,
                   extra_headers: dict = None) -> dict:
    req = urllib.request.Request(url, headers={
        "Authorization": auth,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Language": "en-US,en",
        **(extra_headers or {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        msg = _extract_msg(e.read().decode("utf-8", "replace"))
        raise QuotaError(f"HTTP {e.code}：{msg or e.reason}") from e
    except urllib.error.URLError as e:
        raise QuotaError(f"网络错误：{e.reason}") from e
    except TimeoutError as e:
        raise QuotaError("网络错误：请求超时") from e
    try:
        env = json.loads(body)
    except ValueError as e:
        raise QuotaError("响应不是合法 JSON") from e
    return parse_quota_payload(parse_envelope(env))


def fetch_quota(base, api_key, team=None, timeout: float = 8.0) -> dict:
    """查询一次余额，成功返回 parse_quota_payload 结构，失败抛 QuotaError。

    team={"org","project"} 时走团队套餐路径（?type=2 + 组织/项目头）；
    账户内任意 API key 均可查询团队额度，缺 ID 时抛 QuotaError。
    """
    key = str(api_key or "").strip()
    if not key:
        raise QuotaError("未配置 API Key")
    headers = None
    if team:
        headers = team_headers(team)
        if not headers["Bigmodel-Organization"] or not headers["Bigmodel-Project"]:
            raise QuotaError("团队模式缺少组织/项目 ID")
    url = quota_limit_url(site_root(base), team)
    last_err = None
    # 官方插件裸发 key；个别部署要求 Bearer，401/403 时换前缀重试一次
    for auth in (key, "Bearer " + key):
        try:
            return _http_get_json(url, auth, timeout, extra_headers=headers)
        except QuotaError as e:
            last_err = e
            if "HTTP 401" in str(e) or "HTTP 403" in str(e):
                continue
            raise
    raise last_err


def discover_team_context(zcode_dir=None, base: str = "bigmodel"):
    """从 ZCode 应用凭据键名里发现团队 org/project ID。

    credentials.json 的键形如 project-key-location:v1:<urlencoded JSON>：
    [站点URL, 站点键, 账户ID, {"organizationId":..,"projectId":..}|"non-team", ..]。
    第 4 位是 dict 即团队上下文（键名明文，值是加密的读不了也不需要）。
    优先返回与 base 同站点的条目；找不到返回 None。
    """
    path = Path(zcode_dir) if zcode_dir else Path.home() / ".zcode" / "v2"
    cred = path / "credentials.json"
    try:
        with open(cred, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    site_hint = "bigmodel" if str(base) == "bigmodel" else "z.ai"
    fallback = None
    for k in data.keys():
        if not isinstance(k, str) or not k.startswith("project-key-location:"):
            continue
        # 键名形如 project-key-location:v1:<urlencoded JSON>，剥掉版本段
        payload = k[len("project-key-location:"):]
        if ":" in payload:
            payload = payload.split(":", 1)[1]
        try:
            arr = json.loads(urllib.parse.unquote(payload))
        except ValueError:
            continue
        if not isinstance(arr, list) or len(arr) < 4:
            continue
        ctx = arr[3]
        if not (isinstance(ctx, dict) and ctx.get("organizationId")
                and ctx.get("projectId")):
            continue
        site_str = " ".join(str(x) for x in arr[:2])
        found = {"org": str(ctx["organizationId"]),
                 "project": str(ctx["projectId"])}
        if site_hint in site_str:
            return found
        fallback = fallback or found
    return fallback


from .sources.quota_source import PROVIDER_SPECS, dispatch_provider_quota

# 支持的每行套餐直连渠道枚举：(渠道键, 显示名) — 由 sources 注册表生成
PROVIDER_TYPES = tuple(PROVIDER_SPECS)

_MAGPIE_PROVIDER_NAMES = {
    "zcode": "ZCode",
    "codex": "Codex",
    "codearts": "CodeArts",
    "raccoon": "小浣熊",
    "autoclaw-cn": "AutoClaw",
    "workbuddy-ai": "WorkBuddy",
    "workbuddy": "WorkBuddy",
    "qoder": "Qoder",
    "deepseek": "DeepSeek",
    "moonshot": "Kimi",
    "kimi": "Kimi",
    "openrouter": "OpenRouter",
    "claude": "Claude",
    "anthropic": "Claude",
    "copilot": "Copilot",
}

_MAGPIE_WIN_NAMES = {
    "5 hours": ("5 小时窗口", 18000),
    "weekly": ("每周窗口", 7 * 86400),
    "7 days": ("7 天窗口", 7 * 86400),
    "mcp · month": ("MCP · 本月", 30 * 86400),
    "monthly": ("每月窗口", 30 * 86400),
    "credits": ("可用积分", 30 * 86400),
    "add-on credits": ("附加积分", 30 * 86400),
}


def parse_iso_ms(val):
    """将 ISO8601 时间字符串或毫秒/秒时间戳转为毫秒级 epoch int，无法解析返回 None。"""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return int(val * 1000) if val < 1e11 else int(val)
    if not isinstance(val, str):
        return None
    s = val.strip()
    if not s or s.startswith("9999"):
        return None
    try:
        from datetime import datetime
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def _normalize_magpie_entry(entry: dict, entry_key: str = "") -> dict | None:
    """将 Magpie 单条 quota 记录规整为统一卡片结构。"""
    if not isinstance(entry, dict):
        return None
    q = entry.get("quota") if isinstance(entry.get("quota"), dict) else entry
    provider = str(q.get("provider") or "").strip()
    if not provider and "/" in entry_key:
        provider = entry_key.split("/", 1)[0].strip()
    if not provider:
        return None
    if q.get("error"):
        return None

    user = str(q.get("user") or "").strip()
    card_id = entry_key or (f"{provider}/{user}" if user else provider)
    short_name = _MAGPIE_PROVIDER_NAMES.get(
        provider.lower(),
        str(q.get("name") or provider).strip() or provider,
    )
    plan = str(q.get("plan") or "").strip()
    balance = str(q.get("balance") or "").strip()

    raw_wins = q.get("windows")
    windows = []
    for rw in raw_wins if isinstance(raw_wins, list) else []:
        if not isinstance(rw, dict):
            continue
        raw_name = str(rw.get("name") or "").strip()
        low_name = raw_name.lower()
        # 过滤非真实额度的应用内推广/礼包领取横幅（如 "Gift plans to claim in the ZCode app"）
        if any(k in low_name for k in ("gift plan", "claim in", "promo")):
            continue
        mapped_name, default_span = _MAGPIE_WIN_NAMES.get(low_name, (raw_name or "额度窗口", 0))
        kind = "mcp" if "mcp" in low_name else "tokens"
        span_sec = int(_num(rw.get("span")) or default_span or 0)
        used_pct = _num(rw.get("used"))
        if used_pct is not None:
            used_pct = round(max(0.0, min(100.0, used_pct)), 1)
        rem_pct = _num(rw.get("remaining"))
        if rem_pct is not None:
            rem_pct = round(max(0.0, min(100.0, rem_pct)), 1)
        elif used_pct is not None:
            rem_pct = round(max(0.0, min(100.0, 100.0 - used_pct)), 1)

        amt = _num(rw.get("amount"))
        if amt is not None:
            amt = round(amt, 1) if abs(amt) < 100 else round(amt)
        lim = _num(rw.get("limit"))
        if lim is not None:
            lim = round(lim, 1) if abs(lim) < 100 else round(lim)

        rem_amt = None
        if lim is not None and lim > 0:
            if amt is not None:
                rem_amt = max(0.0, lim - amt)
            elif rem_pct is not None:
                rem_amt = lim * rem_pct / 100.0
            if rem_amt is not None:
                rem_amt = round(rem_amt, 1) if abs(rem_amt) < 100 else round(rem_amt)

        disp = str(rw.get("display") or "").strip()
        if amt is None and lim is not None and lim > 0 and used_pct is not None:
            raw_amt = lim * used_pct / 100.0
            amt = round(raw_amt, 1) if abs(raw_amt) < 100 else round(raw_amt)
        reset_ms = parse_iso_ms(rw.get("resetsAt") or rw.get("runsOutAt"))
        if used_pct is None and rem_pct is None and amt is None and lim is None and not disp:
            continue
        windows.append({
            "kind": kind,
            "name": mapped_name,
            "span_sec": span_sec,
            "percent": used_pct if used_pct is not None else (round(100.0 - rem_pct, 1) if rem_pct is not None else None),
            "used_percent": used_pct,
            "remaining_percent": rem_pct,
            "used": amt,
            "remaining": rem_amt,
            "total": lim,
            "display": disp,
            "reset_ms": reset_ms,
        })

    if not windows and not balance:
        return None

    return {
        "id": card_id,
        "provider": provider,
        "name": short_name,
        "title": short_name,
        "plan": plan,
        "level": plan,
        "user": user,
        "balance": balance,
        "windows": windows,
    }


def parse_magpie_quotas(raw, selected_ids=None, providers_filter=None) -> list[dict]:
    """解析 Magpie HTTP 响应 ({"data": [...]}) 或 ~/.config/magpie/quotas.json 字典。

    同 provider 多账号时优先取有实际用量或首个有效账号；selected_ids 非空时按 id 或 provider 过滤。
    """
    entries = []
    if isinstance(raw, dict):
        if isinstance(raw.get("data"), list):
            for item in raw["data"]:
                norm = _normalize_magpie_entry(item)
                if norm:
                    entries.append(norm)
        else:
            for k, v in raw.items():
                norm = _normalize_magpie_entry(v, entry_key=str(k))
                if norm:
                    entries.append(norm)
    elif isinstance(raw, list):
        for item in raw:
            norm = _normalize_magpie_entry(item)
            if norm:
                entries.append(norm)

    # 按 provider 去重（保留窗口最丰富/用量最高的主账号，避免同一平台重复占满任务栏圆环）
    by_provider = {}
    for e in entries:
        prov = e["provider"]
        score = (
            len(e["windows"]),
            max((w.get("percent") or 0.0 for w in e["windows"]), default=0.0),
            1 if e.get("balance") else 0,
        )
        prev = by_provider.get(prov)
        if prev is None or score > prev[0]:
            by_provider[prov] = (score, e)

    deduped = [pair[1] for pair in by_provider.values()]
    filter_ids = selected_ids or providers_filter
    if filter_ids:
        sel = {str(x).strip().lower() for x in filter_ids if str(x).strip()}
        if sel:
            deduped = [
                e for e in deduped
                if e["id"].lower() in sel
                or e["provider"].lower() in sel
                or e["name"].lower() in sel
            ]
    return deduped


def fetch_magpie_quotas(magpie_url: str = "http://127.0.0.1:3425",
                        quotas_file=None,
                        selected_ids=None,
                        providers_filter=None,
                        timeout: float = 4.0) -> list[dict]:
    """从本机 Magpie 网关（GET /v1/magpie/quotas）及 ~/.config/magpie/quotas.json 获取全部可用套餐。

    网关在线时优先取网关实时数据，并自动补齐本地缓存中离线/未激活但有额度的渠道（如 Codex）。
    """
    http_data = None
    base = str(magpie_url or "http://127.0.0.1:3425").strip().rstrip("/")
    if base.startswith("http://") or base.startswith("https://"):
        url = base if base.endswith("/v1/magpie/quotas") else f"{base}/v1/magpie/quotas"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                http_data = json.loads(resp.read().decode("utf-8", "replace"))
        except Exception:
            http_data = None

    qpath = Path(quotas_file) if quotas_file else (Path.home() / ".config" / "magpie" / "quotas.json")
    file_data = None
    try:
        if qpath.exists():
            with open(qpath, "r", encoding="utf-8") as f:
                file_data = json.load(f)
    except (OSError, ValueError):
        file_data = None

    if http_data is None and file_data is None:
        raise QuotaError("无法连接本机 Magpie 网关（127.0.0.1:3425），且未找到 ~/.config/magpie/quotas.json")

    cards = parse_magpie_quotas(http_data, selected_ids=None) if http_data else []
    seen_provs = {c["provider"] for c in cards}
    if file_data:
        for fc in parse_magpie_quotas(file_data, selected_ids=None):
            if fc["provider"] not in seen_provs:
                cards.append(fc)
                seen_provs.add(fc["provider"])

    filter_ids = selected_ids or providers_filter
    if filter_ids:
        sel = {str(x).strip().lower() for x in filter_ids if str(x).strip()}
        if sel:
            cards = [
                c for c in cards
                if c["id"].lower() in sel
                or c["provider"].lower() in sel
                or c["name"].lower() in sel
            ]
    return cards


def _http_get_raw_json(url: str, headers: dict, timeout: float = 8.0) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        msg = _extract_msg(e.read().decode("utf-8", "replace"))
        raise QuotaError(f"HTTP {e.code}：{msg or e.reason}") from e
    except urllib.error.URLError as e:
        raise QuotaError(f"网络错误：{e.reason}") from e
    except TimeoutError as e:
        raise QuotaError("网络错误：请求超时") from e
    try:
        data = json.loads(body)
    except ValueError as e:
        raise QuotaError("响应不是合法 JSON") from e
    if not isinstance(data, dict):
        raise QuotaError("响应不是 JSON 对象")
    return data


def fetch_deepseek_balance(api_key: str, timeout: float = 8.0) -> dict:
    """查询 DeepSeek 开放平台余额：GET https://api.deepseek.com/user/balance。"""
    key = str(api_key or "").strip()
    if not key:
        raise QuotaError("DeepSeek 缺少 API Key")
    data = _http_get_raw_json(
        "https://api.deepseek.com/user/balance",
        {"Authorization": f"Bearer {key}"},
        timeout=timeout,
    )
    infos = data.get("balance_infos")
    if not isinstance(infos, list) or not infos:
        raise QuotaError("DeepSeek 响应缺少 balance_infos")
    chosen = infos[0]
    for item in infos:
        if isinstance(item, dict) and str(item.get("currency", "")).upper() == "CNY":
            chosen = item
            break
    cur = str(chosen.get("currency", "CNY")).upper()
    sym = "$" if cur == "USD" else "¥"
    total_bal = _num(chosen.get("total_balance")) or 0.0
    bal_str = f"{sym}{total_bal:.2f}"
    return {
        "id": "deepseek",
        "provider": "deepseek",
        "name": "DeepSeek",
        "plan": "API",
        "level": "API",
        "balance": bal_str,
        "status": "ok" if total_bal >= 5.0 else ("warn" if total_bal >= 1.0 else "err"),
        "windows": [
            {
                "kind": "tokens",
                "name": "可用余额",
                "span_sec": 0,
                "percent": 85.0 if total_bal >= 5.0 else (45.0 if total_bal >= 1.0 else 15.0),
                "used": None,
                "total": None,
                "display": bal_str,
                "reset_ms": None,
            }
        ],
    }


def fetch_kimi_balance(api_key: str, base_url: str = "", timeout: float = 8.0) -> dict:
    """查询 Moonshot Kimi 开放平台余额：GET https://api.moonshot.cn/v1/users/me/balance。"""
    key = str(api_key or "").strip()
    if not key:
        raise QuotaError("Kimi 缺少 API Key")
    urls = (
        [f"{base_url.rstrip('/')}/v1/users/me/balance"]
        if base_url and base_url.strip()
        else [
            "https://api.moonshot.cn/v1/users/me/balance",
            "https://api.moonshot.ai/v1/users/me/balance",
        ]
    )
    last_err = None
    data = None
    for u in urls:
        try:
            data = _http_get_raw_json(u, {"Authorization": f"Bearer {key}"}, timeout=timeout)
            break
        except QuotaError as e:
            last_err = e
    if data is None:
        raise last_err or QuotaError("Kimi 查询失败")
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    avail = _num(inner.get("available_balance"))
    if avail is None:
        raise QuotaError("Kimi 响应缺少 available_balance")
    bal_str = f"¥{avail:.2f}"
    return {
        "id": "kimi",
        "provider": "kimi",
        "name": "Kimi",
        "plan": "API",
        "level": "API",
        "balance": bal_str,
        "status": "ok" if avail >= 5.0 else ("warn" if avail >= 1.0 else "err"),
        "windows": [
            {
                "kind": "tokens",
                "name": "可用余额",
                "span_sec": 0,
                "percent": 85.0 if avail >= 5.0 else (45.0 if avail >= 1.0 else 15.0),
                "used": None,
                "total": None,
                "display": bal_str,
                "reset_ms": None,
            }
        ],
    }


def fetch_openrouter_credits(api_key: str, timeout: float = 8.0) -> dict:
    """查询 OpenRouter 额度：GET https://openrouter.ai/api/v1/credits。"""
    key = str(api_key or "").strip()
    if not key:
        raise QuotaError("OpenRouter 缺少 API Key")
    data = _http_get_raw_json(
        "https://openrouter.ai/api/v1/credits",
        {"Authorization": f"Bearer {key}"},
        timeout=timeout,
    )
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    total = _num(inner.get("total_credits"))
    used = _num(inner.get("total_usage")) or 0.0
    if total is None or total <= 0:
        bal_str = f"${max(0.0, (total or 0.0) - used):.2f}"
        return {
            "id": "openrouter",
            "provider": "openrouter",
            "name": "OpenRouter",
            "plan": "Credits",
            "level": "Credits",
            "balance": bal_str,
            "windows": [],
        }
    pct = round(max(0.0, min(100.0, used / total * 100.0)), 1)
    return {
        "id": "openrouter",
        "provider": "openrouter",
        "name": "OpenRouter",
        "plan": "Credits",
        "level": "Credits",
        "used": round(used, 2),
        "limit": round(total, 2),
        "unit": "USD",
        "windows": [
            {
                "kind": "tokens",
                "name": "总额度",
                "span_sec": 30 * 86400,
                "percent": pct,
                "used": round(used, 2),
                "total": round(total, 2),
                "display": f"${used:.2f} / ${total:.2f}",
                "reset_ms": None,
            }
        ],
    }


def discover_codex_auth() -> dict | None:
    """自动从 ~/.codex/auth.json 或 ~/.config/magpie/logins.json 发现 ChatGPT Codex OAuth 凭据。"""
    candidates = [
        Path.home() / ".codex" / "auth.json",
        Path.home() / ".config" / "magpie" / "logins.json",
    ]
    for p in candidates:
        try:
            if not p.exists():
                continue
            with open(p, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                tokens = raw.get("tokens") if isinstance(raw.get("tokens"), dict) else raw
                acc = tokens.get("access_token")
                if acc:
                    return {
                        "access_token": str(acc),
                        "account_id": str(tokens.get("account_id") or ""),
                        "plan": "Plus",
                    }
            elif isinstance(raw, list):
                for entry in raw:
                    if not isinstance(entry, dict) or entry.get("agent") != "codex":
                        continue
                    auth = entry.get("auth") or {}
                    tokens = auth.get("tokens") or {}
                    acc = tokens.get("access_token")
                    if acc:
                        return {
                            "access_token": str(acc),
                            "account_id": str(tokens.get("account_id") or ""),
                            "plan": str(entry.get("plan") or "Plus"),
                        }
        except (OSError, ValueError):
            continue
    return None


def fetch_codex_usage(api_key: str = "", timeout: float = 8.0) -> dict:
    """查询 ChatGPT Codex (Plus/Pro/Team) 5h & 7d 窗口用量，离线时回退本机 Magpie 缓存。"""
    token = str(api_key or "").strip()
    account_id = ""
    plan = "Plus"
    if not token:
        found = discover_codex_auth()
        if found:
            token = found["access_token"]
            account_id = found.get("account_id", "")
            plan = found.get("plan", "Plus")

    if token:
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "codex-cli/0.1.0",
        }
        if account_id:
            headers["ChatGPT-Account-Id"] = account_id
        try:
            data = _http_get_raw_json(
                "https://chatgpt.com/backend-api/wham/usage",
                headers,
                timeout=timeout,
            )
            plan = str(data.get("plan_type") or plan).strip()
            rl = data.get("rate_limit") or {}
            windows = []
            for key_name, label, span in (
                ("primary_window", "5 小时窗口", 18000),
                ("secondary_window", "7 天窗口", 7 * 86400),
            ):
                w = rl.get(key_name)
                if isinstance(w, dict) and _num(w.get("used_percent")) is not None:
                    pct = round(max(0.0, min(100.0, float(_num(w["used_percent"])))), 1)
                    rem_pct = round(max(0.0, min(100.0, 100.0 - pct)), 1)
                    reset_ms = parse_iso_ms(w.get("reset_at"))
                    windows.append({
                        "kind": "tokens",
                        "name": label,
                        "span_sec": int(_num(w.get("limit_window_seconds")) or span),
                        "percent": pct,
                        "used_percent": pct,
                        "remaining_percent": rem_pct,
                        "used": pct,
                        "remaining": rem_pct,
                        "total": 100.0,
                        "display": f"{int(round(rem_pct))}%",
                        "reset_ms": reset_ms,
                    })
            if windows:
                return {
                    "id": "codex",
                    "provider": "codex",
                    "name": "Codex",
                    "plan": plan,
                    "level": plan,
                    "windows": windows,
                }
        except QuotaError:
            pass

    # 回退：从本机 Magpie quotas.json 读取最近一次 Codex 记录
    try:
        cards = fetch_magpie_quotas(selected_ids=["codex"], timeout=2.0)
        if cards:
            return cards[0]
    except QuotaError:
        pass
    raise QuotaError("无法获取 ChatGPT Codex 用量（请确认已登录 Codex 或 Magpie）")


def fetch_newapi_usage(api_key: str, base_url: str, timeout: float = 8.0) -> dict:
    """查询 NewAPI / OneAPI 通用中转站令牌额度：GET {base_url}/api/usage/token。"""
    key = str(api_key or "").strip()
    base = str(base_url or "").strip().rstrip("/")
    if not key or not base:
        raise QuotaError("NewAPI 缺少接口地址或 API Key")
    data = _http_get_raw_json(
        f"{base}/api/usage/token",
        {"Authorization": f"Bearer {key}"},
        timeout=timeout,
    )
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    used_raw = _num(inner.get("total_used")) or 0.0
    avail_raw = _num(inner.get("total_available")) or 0.0
    granted_raw = _num(inner.get("total_granted")) or (used_raw + avail_raw)
    # NewAPI 默认 500000 = $1.00
    scale = 500000.0 if granted_raw > 10000 else 1.0
    used = round(used_raw / scale, 2)
    total = round(granted_raw / scale, 2)
    if total <= 0:
        raise QuotaError("NewAPI 返回总额度为 0")
    pct = round(max(0.0, min(100.0, used / total * 100.0)), 1)
    return {
        "id": "newapi",
        "provider": "newapi",
        "name": "NewAPI",
        "plan": "Relay",
        "level": "Relay",
        "used": used,
        "limit": total,
        "unit": "USD",
        "windows": [
            {
                "kind": "tokens",
                "name": "令牌额度",
                "span_sec": 30 * 86400,
                "percent": pct,
                "used": used,
                "total": total,
                "display": f"${used:.2f} / ${total:.2f}",
                "reset_ms": None,
            }
        ],
    }


def fetch_provider_quota(item: dict, timeout: float = 8.0) -> dict:
    """按套餐行配置的 provider 类型分派实时查询（通过注册表分派）。"""
    return dispatch_provider_quota(item, timeout=timeout)


def fetch_claude_usage(*args, **kwargs):
    from .sources.claude_source import fetch_claude_usage as _fn
    return _fn(*args, **kwargs)


def fetch_cursor_usage(*args, **kwargs):
    from .sources.cursor_source import fetch_cursor_usage as _fn
    return _fn(*args, **kwargs)


def fetch_openai_usage(*args, **kwargs):
    from .sources.deepseek_source import fetch_openai_usage as _fn
    return _fn(*args, **kwargs)


class QuotaService(QObject):
    """定时后台查询多渠道额度（Magpie 聚合网关 / GLM 直连 / 行级多渠道直连），经 updated 信号投递回主线程。

    status 字段在主线程维护：ok 态 {"state", "ts", "level", "windows", "cards", "row_updates"}；
    error 态保留上一次成功的 windows/cards 供 UI 展示旧值，附 last_ok_ts。
    """

    updated = Signal(dict)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self.status = {"state": "idle"}
        self._busy = False
        self._sig = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self.updated.connect(self._store)
        self.configure(cfg)

    @staticmethod
    def _auto_rows_sig(cfg: dict) -> tuple:
        rows = []
        for idx, q in enumerate(cfg.get("quotas") or []):
            if not isinstance(q, dict):
                continue
            prov = str(q.get("provider") or "manual").strip().lower()
            if prov != "manual":
                rows.append((idx, prov, str(q.get("name") or ""),
                             str(q.get("apiKey") or "").strip(),
                             str(q.get("baseUrl") or "").strip()))
        return tuple(rows)

    def configure(self, cfg: dict):
        """应用配置：开关/间隔变化重启定时器，凭据或数据源变化立即刷新一次。"""
        self._cfg = cfg
        qa = cfg.get("quotaApi") or {}
        source = str(qa.get("source", "glm"))
        key = str(qa.get("apiKey", "")).strip()
        qa_enabled = bool(qa.get("enabled")) and (source == "magpie" or bool(key))
        rows_sig = self._auto_rows_sig(cfg)
        enabled = qa_enabled or bool(rows_sig)
        try:
            interval = int(qa.get("intervalMin", 10))
        except (TypeError, ValueError):
            interval = 10
        interval = max(1, min(720, interval))
        self._timer.setInterval(interval * 60 * 1000)
        sig = (
            qa_enabled,
            source,
            str(qa.get("magpieUrl", "http://127.0.0.1:3425")),
            tuple(qa.get("magpieProviders") or []),
            str(qa.get("base", "bigmodel")),
            key,
            str(qa.get("scope", "personal")),
            str(qa.get("orgId", "")),
            str(qa.get("projectId", "")),
            rows_sig,
        )
        changed = sig != self._sig
        self._sig = sig
        if not enabled:
            self._timer.stop()
            return
        self._timer.start()
        if changed:
            self.refresh()

    @staticmethod
    def _team_of(qa: dict):
        """配置 → 团队上下文；个人模式返回 None。"""
        if str(qa.get("scope", "personal")) != "team":
            return None
        return {"org": str(qa.get("orgId", "")),
                "project": str(qa.get("projectId", ""))}

    def refresh(self):
        if self._busy:
            return
        qa = self._cfg.get("quotaApi") or {}
        source = str(qa.get("source", "glm"))
        key = str(qa.get("apiKey", "")).strip()
        qa_enabled = bool(qa.get("enabled")) and (source == "magpie" or bool(key))
        auto_rows = [
            (idx, dict(q))
            for idx, q in enumerate(self._cfg.get("quotas") or [])
            if isinstance(q, dict) and str(q.get("provider") or "manual").lower() != "manual"
        ]
        if not qa_enabled and not auto_rows:
            return
        base = str(qa.get("base", "bigmodel"))
        team = self._team_of(qa)
        magpie_url = str(qa.get("magpieUrl", "http://127.0.0.1:3425"))
        magpie_provs = list(qa.get("magpieProviders") or [])
        self._busy = True

        def _work():
            cards = []
            row_updates = {}
            errors = []
            if qa_enabled and not auto_rows:
                try:
                    if source == "magpie":
                        cards.extend(fetch_magpie_quotas(
                            magpie_url=magpie_url,
                            selected_ids=magpie_provs,
                        ))
                    else:
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
                except Exception as e:  # noqa: BLE001
                    errors.append(str(e))
                    _q_logger.info("fetch primary fail err=%s", str(e)[:160])

            for idx, row_item in auto_rows:
                try:
                    res = fetch_provider_quota(row_item)
                    row_updates[idx] = res
                    if res.get("windows"):
                        cards.append(res)
                except Exception as e:  # noqa: BLE001
                    errors.append(str(e))
                    _q_logger.info("fetch row[%d] fail err=%s", idx, str(e)[:160])

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
                }
                _q_logger.info("fetch ok cards=%d rows=%d", len(cards), len(row_updates))
            else:
                err_msg = "; ".join(errors) if errors else "未获取到任何有效套餐数据"
                state = {"state": "error", "ts": time.time(), "error": err_msg}
            self.updated.emit(state)

        threading.Thread(target=_work, daemon=True).start()

    def _store(self, state: dict):
        self._busy = False
        if state.get("state") == "ok":
            self.status = state
            return
        prev = self.status
        if prev.get("state") == "ok":
            state["windows"] = prev.get("windows")
            state["cards"] = prev.get("cards")
            state["row_updates"] = prev.get("row_updates")
            state["last_ok_ts"] = prev.get("ts")
        self.status = state
