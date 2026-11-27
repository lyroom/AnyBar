"""app/tiles.py — 统一 Tile 数据模型与归一化逻辑（纯逻辑，无 Qt 依赖）

将各类数据源（算力额度、系统资源、股票、天气等）统一归一化为标准的 Tile 数据结构。
供任务栏常驻条 (BarWidget) 与悬停面板 (HoverPanel) 消费。
"""

from __future__ import annotations

import re
import time
from typing import Any

# 默认阶梯语义色板（无 Qt 依赖环境兜底）
DEFAULT_PALETTE = {
    "quota_green": "#34C759",
    "quota_amber": "#FF9500",
    "quota_red": "#FF3B30",
    "quota_blue": "#007AFF",
}


def _balance_is_zero(raw: str) -> bool:
    """判断余额文本（如 '0 积分'、'¥0.00'、'$0'）是否为零。"""
    m = re.search(r"-?\d+(?:\.\d+)?", str(raw or ""))
    if not m:
        return False
    try:
        return float(m.group(0)) <= 0.0
    except ValueError:
        return False


def fmt_num(v: Any, compact: bool = True) -> str:
    """数值缩写格式化：>=10000 压为 x.xk / xk，保留合理有效数字。"""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        fv = float(v)
        if compact and abs(fv) >= 10000:
            kv = fv / 1000.0
            if abs(kv) >= 100 or abs(kv - round(kv)) < 0.05:
                return f"{int(round(kv))}k"
            return f"{kv:.1f}k"
        if abs(fv) >= 100 or abs(fv - round(fv)) < 0.05:
            return str(int(round(fv)))
        return f"{round(fv, 1):g}"
    return str(v)


def ratio_to_color(ratio: float, palette: dict[str, str] | None = None) -> str:
    """根据比率 (0.0~1.0) 返回阶梯语义色（>50% 绿, 20%~50% 橙, <=20% 红）。"""
    pal = palette or DEFAULT_PALETTE
    if ratio > 0.50:
        return pal.get("quota_green", "#34C759")
    if ratio > 0.20:
        return pal.get("quota_amber", "#FF9500")
    return pal.get("quota_red", "#FF3B30")


def make_tile(
    id: str,
    source: str,
    name: str,
    ratio: float | None = None,
    center_text: str = "",
    sub_text: str = "",
    color: str | None = None,
    kind: str = "ring",
    status: str = "ok",
    updated_at: float | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """构造标准的 Tile 数据字典。

    同时输出 frac / pct 兼容旧版 BarWidget 绘制字段。
    """
    if ratio is not None:
        clamped_ratio = max(0.0, min(1.0, float(ratio)))
    else:
        clamped_ratio = None

    resolved_color = color or (ratio_to_color(clamped_ratio) if clamped_ratio is not None else "#34C759")
    now_ts = time.time() if updated_at is None else float(updated_at)

    tile: dict[str, Any] = {
        "id": str(id),
        "source": str(source),
        "name": str(name),
        "kind": str(kind),
        "ratio": clamped_ratio,
        "center_text": str(center_text),
        "sub_text": str(sub_text),
        "color": str(resolved_color),
        "status": str(status),
        "updated_at": now_ts,
        # 向后兼容字段：
        "frac": clamped_ratio if clamped_ratio is not None else 0.85,
        "pct": str(center_text),
    }
    if extra:
        tile.update(extra)
    return tile


def find_primary_window(windows: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """取主展示窗口：tokens 类中时长最短者（GLM 套餐即 5 小时窗）。"""
    cands = [
        w for w in (windows or [])
        if isinstance(w, dict) and w.get("kind") == "tokens" and w.get("percent") is not None
    ]
    if not cands:
        return None

    def _rank(w: dict[str, Any]) -> int:
        s = w.get("span_sec") or 0
        return s if s > 0 else 1 << 30

    return min(cands, key=_rank)


def card_to_tile(card: dict[str, Any], palette: dict[str, str] | None = None) -> dict[str, Any] | None:
    """将单个自动查询卡片（Magpie / GLM / Codex 等）转换为标准 Tile 项。"""
    name = str(card.get("name") or card.get("provider") or "AI").strip()
    wins = card.get("windows") or []
    w = find_primary_window(wins)
    pal = palette or DEFAULT_PALETTE

    if w is not None:
        rem_pct = w.get("remaining_percent")
        if rem_pct is None and w.get("percent") is not None:
            rem_pct = round(max(0.0, min(100.0, 100.0 - float(w["percent"]))), 1)
        if rem_pct is not None:
            pct = float(rem_pct)
            ratio = max(0.0, min(1.0, pct / 100.0))
            color = ratio_to_color(ratio, pal)
            pct_s = f"{int(round(pct))}%"
            rem_amt = w.get("remaining")
            if rem_amt is None and w.get("used") is not None and w.get("total") is not None:
                rem_amt = max(0.0, w["total"] - w["used"])
            if rem_amt is not None and w.get("total") is not None and w["total"] > 100:
                sub_s = f"{fmt_num(rem_amt)}/{fmt_num(w['total'])}"
            elif w.get("display"):
                sub_s = str(w["display"])
            else:
                sub_s = f"5h {pct_s}"

            card_id = f"{card.get('provider') or 'quota'}:{name}"
            return make_tile(
                id=card_id,
                source="quota",
                name=name,
                ratio=ratio,
                center_text=pct_s,
                sub_text=sub_s,
                color=color,
                kind="ring",
                status="ok",
            )

    bal = str(card.get("balance") or "").strip()
    if not bal and wins:
        bal = str(wins[0].get("display") or "").strip()
    if bal:
        card_id = f"{card.get('provider') or 'quota'}:{name}"
        is_zero = _balance_is_zero(bal)
        ratio = 0.0 if is_zero else 0.85
        col = pal.get("quota_red", "#FF3B30") if is_zero else pal.get("quota_green", "#34C759")
        center_sym = "0" if is_zero else ("¥" if "¥" in bal else ("$" if "$" in bal else "积分"))
        return make_tile(
            id=card_id,
            source="quota",
            name=name,
            ratio=ratio,
            center_text=center_sym,
            sub_text=bal,
            color=col,
            kind="ring",
            status="err" if is_zero else "ok",
        )
    return None


def tiles_from_quota_state(
    quota_state: dict[str, Any] | None,
    cfg: dict[str, Any] | None = None,
    palette: dict[str, str] | None = None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    """取有效套餐的前 limit 个，附百分比/余额与颜色。

    优先按用户「算力套餐管理」列表 (cfg['quotas']) 的顺序与设置展示；
    若用户列表为空，则回退展示自动拉取的 cards/windows 项。
    """
    out: list[dict[str, Any]] = []
    cfg_dict = cfg or {}
    st = quota_state or {}
    pal = palette or DEFAULT_PALETTE

    row_updates = st.get("row_updates") or {}
    for idx, raw_q in enumerate(cfg_dict.get("quotas", []) or []):
        if not isinstance(raw_q, dict):
            continue
        q = dict(raw_q)
        if idx in row_updates and isinstance(row_updates[idx], dict):
            upd = row_updates[idx]
            for k in ("used", "limit", "unit", "balance", "status"):
                if upd.get(k) is not None:
                    q[k] = upd[k]
        name = str(q.get("name", "")).strip()
        if not name:
            continue
        used, lim = q.get("used"), q.get("limit")
        unit = str(q.get("unit", "") or "").strip()
        has_balance = bool(str(q.get("balance", q.get("value", "")) or "").strip())

        if (
            isinstance(used, (int, float))
            and isinstance(lim, (int, float))
            and lim > 0
            and not has_balance
        ):
            ratio = max(0.0, min(1.0, float(used) / float(lim)))
            pct_text = f"{int(round(ratio * 100))}%"
            center_text = pct_text
            if unit == "%" and lim == 100:
                sub_text = f"5h {pct_text}"
            else:
                sub_text = f"{fmt_num(used)}/{fmt_num(lim)}"
        else:
            raw = q.get("balance", q.get("value"))
            raw_str = str(raw if raw is not None else "").strip()
            status = str(q.get("status", "ok")).lower()
            if raw_str and _balance_is_zero(raw_str):
                ratio = 0.0
            else:
                ratio = {"ok": 0.85, "warn": 0.45, "err": 0.15}.get(status, 0.85)
            if raw_str:
                if isinstance(raw, (int, float)) or raw_str.replace(".", "", 1).isdigit():
                    pct_text = f"¥{raw_str}"
                else:
                    pct_text = raw_str
            else:
                pct_text = f"{int(round(ratio * 100))}%"
            center_text = "0" if ratio <= 0.0 else ("¥" if "¥" in pct_text else ("$" if "$" in pct_text else f"{int(round(ratio * 100))}%"))
            sub_text = pct_text

        color = ratio_to_color(ratio, pal)
        tile_item = make_tile(
            id=f"cfg_quota:{idx}",
            source="quota",
            name=name,
            ratio=ratio,
            center_text=center_text,
            sub_text=sub_text,
            color=color,
            kind="ring",
            status=str(q.get("status", "ok")),
        )
        out.append(tile_item)
        if len(out) >= limit:
            break

    if out:
        return out

    # 用户未配置明细套餐，回退到自动查询 cards / windows
    qa = cfg_dict.get("quotaApi") or {}
    if not qa.get("enabled") or not qa.get("showOnBar", True):
        return []

    cards = st.get("cards")
    if isinstance(cards, list) and cards:
        auto_out: list[dict[str, Any]] = []
        for c in cards:
            if not isinstance(c, dict):
                continue
            tile = card_to_tile(c, pal)
            if tile:
                auto_out.append(tile)
            if len(auto_out) >= limit:
                break
        return auto_out

    if st.get("windows"):
        single = card_to_tile({"name": "GLM", "windows": st["windows"]}, pal)
        return [single] if single else []

    return []
