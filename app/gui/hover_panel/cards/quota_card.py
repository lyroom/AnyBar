"""app/gui/hover_panel/cards/quota_card.py — 算力套餐与额度卡片（内聚 QuotaTile 与原位更新）"""

from __future__ import annotations

import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.core import quota_api
from app.gui import widgets as ui_parts
from app.styles import tokens

from ..primitives import (
    InnerTile,
    SmoothProgressBar,
    TierCard,
    apply_label_color,
    make_card_header,
    make_label,
    make_transparent_widget,
    ui_font,
)
from .base import BasePanelCard, PanelCardContext


class QuotaTile(InnerTile):
    """算力套餐嵌套子卡（8px 同心圆角 + 呼吸玻璃灯珠 + 轻拟物液态进度条 + 跟手镜面光泽）。"""

    def __init__(self, data: dict, dark: bool, index: int, scale: float,
                 wide: bool = True, parent: QWidget | None = None):
        super().__init__(dark=dark, scale=scale, interactive=True, accent_hover=True, parent=parent)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._dark = dark
        self._scale = scale
        t = tokens.get_tokens(dark)
        self.setObjectName("quotaBentoTile")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        v = QVBoxLayout(self)
        pad_x = tokens.spx(11, scale, lo=8)
        pad_y = tokens.spx(8, scale, lo=5)
        v.setContentsMargins(pad_x, pad_y, pad_x, pad_y)
        v.setSpacing(tokens.spx(5, scale, lo=3))

        head = make_transparent_widget()
        hh = QHBoxLayout(head)
        hh.setContentsMargins(0, 0, 0, 0)
        hh.setSpacing(tokens.spx(6, scale))

        self._dot = ui_parts.PulseStatusDot(t.ok_solid, scale, animated=True)
        hh.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)

        self.name_lbl = make_label("—", 12.5 * scale, t.text, 700, role="primary")
        hh.addWidget(self.name_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        self._plan_lbl = QLabel("")
        self._plan_lbl.setObjectName("planBadge")
        self._plan_lbl.setFont(ui_font(10 * scale, 600))
        self._plan_lbl.hide()
        hh.addWidget(self._plan_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        hh.addStretch(1)

        self.value_lbl = make_label("", 12 * scale, t.text, 700, mono=True, role="primary")
        self.value_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hh.addWidget(self.value_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        v.addWidget(head)

        self.bar = SmoothProgressBar(dark, t.ok_solid, scale)
        v.addWidget(self.bar)

        self._foot = make_transparent_widget()
        fh = QHBoxLayout(self._foot)
        fh.setContentsMargins(0, 0, 0, 0)
        fh.setSpacing(tokens.spx(6, scale))
        self._sec_lbl = make_label("", 10.5 * scale, t.text_secondary, 500, wrap=False, role="secondary")
        self._sec_lbl.setMinimumWidth(0)
        fh.addWidget(self._sec_lbl, 1, Qt.AlignmentFlag.AlignVCenter)
        self._reset_lbl = make_label("", 10.5 * scale, t.text_muted, 500, mono=True, role="muted")
        fh.addWidget(self._reset_lbl, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._foot.hide()
        v.addWidget(self._foot)

        self.update_data(data)

    def update_data(self, data: dict) -> None:
        dark = self._dark
        name = str(data.get("name") or data.get("title") or data.get("provider") or "—").strip()
        plan = str(data.get("plan") or data.get("level") or "").strip()

        wins = data.get("windows") or []
        prim_w = quota_api.primary_window(wins) if wins else None

        used = data.get("used")
        limit = data.get("limit")
        raw_unit = str(data.get("unit", "") or "").strip()
        has_balance = bool(str(data.get("balance", data.get("value", "")) or "").strip())

        rem_pct = None
        rem_amt = None
        tot_amt = None
        prim_label = ""
        reset_str = ""

        if prim_w is not None:
            w_name = str(prim_w.get("name") or "").strip()
            if "5" in w_name or "小时" in w_name:
                prim_label = "5h "
            elif "7" in w_name or "周" in w_name:
                prim_label = "本周 "
            rem_pct = prim_w.get("remaining_percent")
            if rem_pct is None and prim_w.get("percent") is not None:
                rem_pct = round(max(0.0, min(100.0, 100.0 - float(prim_w["percent"]))), 1)
            rem_amt = prim_w.get("remaining")
            if rem_amt is None and prim_w.get("used") is not None and prim_w.get("total") is not None:
                rem_amt = max(0.0, float(prim_w["total"]) - float(prim_w["used"]))
            tot_amt = prim_w.get("total")
            if prim_w.get("reset_ms"):
                now_dt = datetime.datetime.now()
                now_ms = now_dt.timestamp() * 1000.0
                if float(prim_w["reset_ms"]) > now_ms:
                    reset_dt = datetime.datetime.fromtimestamp(prim_w["reset_ms"] / 1000.0)
                    fmt = "%H:%M" if reset_dt.date() == now_dt.date() else "%m-%d %H:%M"
                    reset_str = f"{reset_dt.strftime(fmt)} 重置"

        has_count = (
            isinstance(used, (int, float))
            and isinstance(limit, (int, float))
            and limit > 0
            and not has_balance
        )
        if has_count:
            frac = max(0.0, min(1.0, float(used) / float(limit)))
            if rem_pct is None:
                rem_pct = round(frac * 100.0, 1)
            if limit > 100 and raw_unit != "%":
                rem_amt = used
                tot_amt = limit
        elif rem_pct is not None:
            frac = max(0.0, min(1.0, float(rem_pct) / 100.0))
        else:
            status = str(data.get("status", "ok")).lower()
            frac = {"ok": 0.85, "warn": 0.45, "err": 0.15}.get(status, 0.85)

        pct_int = int(round(frac * 100))
        if rem_amt is not None and tot_amt is not None and tot_amt > 100:
            value_main = f"剩余 {pct_int}% ({self._fmt(rem_amt)}/{self._fmt(tot_amt)})"
        elif rem_pct is not None or has_count:
            value_main = f"{prim_label}剩余 {pct_int}%"
        else:
            value_main = str(data.get("balance", data.get("value", "—")))

        bar_color, val_color = tokens.quota_tier_colors(frac, dark)
        val_role = "danger" if frac <= 0.20 else ("warn" if frac <= 0.50 else "ok")

        self._dot.set_color(bar_color)
        self._dot.set_urgent(frac <= 0.20)
        self.name_lbl.setText(name)
        if plan:
            self._plan_lbl.setText(plan)
            self._plan_lbl.show()
        else:
            self._plan_lbl.hide()

        self.value_lbl.setText(value_main)
        apply_label_color(self.value_lbl, val_color, role=val_role)

        self.bar.set_color(bar_color)
        self.bar.set_ratio(frac)

        sec_parts = []
        for w in wins:
            if w is prim_w:
                continue
            wn = str(w.get("name") or "").strip()
            if any(k in wn.lower() for k in ("gift plan", "claim in", "promo")):
                continue
            wn_short = wn.replace("窗口", "").replace("积分包", "包").replace(" · 本月", "")
            w_rem_amt = w.get("remaining")
            if w_rem_amt is None and w.get("used") is not None and w.get("total") is not None:
                w_rem_amt = max(0.0, float(w["total"]) - float(w["used"]))
            w_rem_pct = w.get("remaining_percent")
            if w_rem_pct is None and w.get("percent") is not None:
                w_rem_pct = round(max(0.0, min(100.0, 100.0 - float(w["percent"]))), 1)
            if w_rem_amt is not None and w.get("total") is not None and w["total"] > 100:
                sec_parts.append(f"{wn_short}余 {self._fmt(w_rem_amt)}/{self._fmt(w['total'])}")
            elif w_rem_pct is not None:
                sec_parts.append(f"{wn_short}余 {int(round(w_rem_pct))}%")

        if sec_parts or reset_str:
            self._sec_lbl.setText("  ·  ".join(sec_parts) if sec_parts else "")
            self._reset_lbl.setText(reset_str if reset_str else "")
            self._reset_lbl.setVisible(bool(reset_str))
            self._foot.show()
        else:
            self._foot.hide()

    @staticmethod
    def _fmt(v) -> str:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            fv = float(v)
            if abs(fv) >= 100 or abs(fv - round(fv)) < 0.05:
                return str(int(round(fv)))
            return f"{round(fv, 1):g}"
        return str(v)


def _quota_has_data(q: dict) -> bool:
    for key in ("used", "limit", "balance", "value"):
        val = q.get(key)
        if isinstance(val, (int, float)):
            return True
        if isinstance(val, str) and val.strip():
            return True
    return False


def collect_quotas_data(cfg: dict, quota_state: dict | None, source_tiles: dict) -> list[dict]:
    """合并配置文件中的套餐、QuotaService 实时状态与独立算力数据源 Tiles。"""
    state = quota_state or {}
    row_updates = state.get("row_updates") or {}
    state_cards = state.get("cards") or []
    card_by_key = {}
    for sc in state_cards:
        if isinstance(sc, dict):
            for k in (sc.get("provider"), sc.get("name"), sc.get("title")):
                if k:
                    card_by_key[str(k).strip().lower()] = sc

    quotas = []
    for idx, q in enumerate(cfg.get("quotas") or []):
        if not isinstance(q, dict) or not str(q.get("name", "")).strip():
            continue
        merged = dict(q)
        if idx in row_updates and isinstance(row_updates[idx], dict):
            for k, val in row_updates[idx].items():
                if val is not None:
                    merged[k] = val
        if not merged.get("windows"):
            for lookup in (merged.get("apiKey"), merged.get("name"), merged.get("provider")):
                sc = card_by_key.get(str(lookup or "").strip().lower())
                if sc:
                    if sc.get("windows"):
                        merged["windows"] = sc["windows"]
                    if sc.get("plan") and not merged.get("plan"):
                        merged["plan"] = sc["plan"]
                    break
        if _quota_has_data(merged) or merged.get("windows"):
            quotas.append(merged)

    for s_id, def_name in (
        ("claude_quota", "Claude"),
        ("cursor_quota", "Cursor"),
        ("deepseek_quota", "DeepSeek"),
    ):
        for st in source_tiles.get(s_id) or []:
            t_name = str(st.get("name") or def_name).strip()
            if any(str(q.get("name") or "").lower() == t_name.lower() for q in quotas):
                continue
            q_item = {
                "id": st.get("id"),
                "name": t_name,
                "provider": s_id.split("_")[0],
                "value": st.get("center_text"),
                "balance": st.get("sub_text"),
                "status": st.get("status", "ok"),
            }
            if st.get("ratio") is not None:
                q_item["used"] = int(round(float(st["ratio"]) * 100))
                q_item["limit"] = 100
                q_item["unit"] = "%"
            quotas.append(q_item)

    if not quotas and state_cards:
        quotas = [dict(c) for c in state_cards if isinstance(c, dict)]
    return quotas


class QuotaPanelCard(BasePanelCard):
    """算力与额度卡片控制器：负责 QuotaTile 列表渲染、原位刷新与入场动画。"""

    card_id = "quotas"
    aliases = ("tiles",)
    source_ids = ("quota", "claude_quota", "cursor_quota", "deepseek_quota")

    def __init__(self) -> None:
        self.card: QWidget | None = None
        self.header_lbl: QLabel | None = None
        self.tiles: list[QuotaTile] = []
        self.keys: list[str] = []

    def reset(self) -> None:
        self.card = None
        self.header_lbl = None
        self.tiles = []
        self.keys = []

    def build(self, ctx: PanelCardContext) -> QWidget | None:
        quotas = collect_quotas_data(ctx.cfg, ctx.quota_state, ctx.source_tiles)
        if not quotas:
            return None

        dark, scale = ctx.dark, ctx.scale
        t = tokens.get_tokens(dark)
        sp = lambda v, lo=1: tokens.spx(v, scale, lo=lo)

        card = TierCard(dark, scale)
        v = QVBoxLayout(card)
        v.setContentsMargins(sp(14, 10), sp(11, 7), sp(14, 10), sp(11, 7))
        v.setSpacing(sp(7, 4))

        state = ctx.quota_state or {}
        right = f"{len(quotas)} 个套餐在线"
        ts = state.get("ts") or state.get("last_ok_ts")
        if ts:
            right += f" · {datetime.datetime.fromtimestamp(float(ts)).strftime('%H:%M')} 更新"
        self.header_lbl = make_label(right, 10.5 * scale, t.text_muted, 500, mono=True, role="muted")
        v.addWidget(make_card_header("spark", t.violet, "算力与额度", self.header_lbl, dark, scale))

        self.card = card
        self.tiles = []
        self.keys = []
        for idx, q in enumerate(quotas[:6]):
            tile = QuotaTile(q, dark, idx, scale, wide=True)
            v.addWidget(tile)
            self.tiles.append(tile)
            self.keys.append(str(q.get("name") or q.get("title") or q.get("provider") or "").strip())
        return card

    def try_update_inplace(self, source_id: str, ctx: PanelCardContext) -> bool:
        if self.card is None or not self.tiles or self.card.parent() is None:
            return False

        quotas = collect_quotas_data(ctx.cfg, ctx.quota_state, ctx.source_tiles)
        visible_quotas = quotas[:6]
        new_keys = [
            str(q.get("name") or q.get("title") or q.get("provider") or "").strip()
            for q in visible_quotas
        ]
        if new_keys != self.keys:
            return False

        state = ctx.quota_state or {}
        if self.header_lbl is not None:
            right = f"{len(quotas)} 个套餐在线"
            ts = state.get("ts") or state.get("last_ok_ts")
            if ts:
                right += f" · {datetime.datetime.fromtimestamp(float(ts)).strftime('%H:%M')} 更新"
            self.header_lbl.setText(right)

        for tile, q_data in zip(self.tiles, visible_quotas):
            tile.update_data(q_data)
        return True

    def play_entrance(self) -> None:
        for idx, tile in enumerate(self.tiles):
            if getattr(tile, "bar", None) is not None:
                tile.bar.play_entrance(delay_ms=50 + idx * 75)

    def stop_animations(self) -> None:
        for tile in self.tiles:
            if getattr(tile, "bar", None) is not None:
                tile.bar.stop_entrance()
