"""app/gui/hover_panel/cards/schedule_card.py — 日程焦点卡片（含平滑全天日程抽屉）"""

from __future__ import annotations

import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from app.core import config as config_mod
from app.gui import widgets as ui_parts
from app.gui.widgets import motion
from app.styles import icons, qss_engine, tokens

from ..primitives import (
    Badge,
    Divider,
    SmoothProgressBar,
    TierCard,
    apply_label_color,
    make_ghost_link,
    make_label,
    make_transparent_widget,
)
from .base import BasePanelCard, PanelCardContext


def format_remain_text(frac: float, cur) -> str:
    if not cur:
        return "自由时间"
    try:
        sh, sm = map(int, str(cur.get("start", "0:0")).split(":"))
        eh, em = map(int, str(cur.get("end", "23:59")).split(":"))
    except ValueError:
        return f"{int(round(frac * 100))}%"
    total = (eh * 60 + em) - (sh * 60 + sm)
    if total <= 0:
        return f"{int(round(frac * 100))}%"
    left = max(0, int(round(total * (1.0 - frac))))
    h, m = divmod(left, 60)
    if h and m:
        return f"剩余 {h}h {m}m"
    if h:
        return f"剩余 {h}h"
    return f"剩余 {m}m"


class DayList(QWidget):
    """全天日程明细列表，样式由 hover_panel.qss 的 #dayRow[active='true'] 驱动。"""

    def __init__(self, dark: bool, scale: float, parent: QWidget | None = None):
        super().__init__(parent)
        self._scale = scale
        self._dark = dark
        self._last_sig = None
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(0, tokens.spx(6, scale), 0, tokens.spx(2, scale))
        self._v.setSpacing(tokens.spx(4, scale))

    def set_schedule(self, items, cur) -> None:
        cur_sig = (cur.get("start"), cur.get("text")) if isinstance(cur, dict) else None
        items_sig = tuple(
            (str(e.get("start", "")), str(e.get("end", "")), str(e.get("text", "")))
            for e in (items or [])
            if isinstance(e, dict)
        )
        sig = (items_sig, cur_sig)
        if sig == self._last_sig and self._v.count() > 0:
            return
        self._last_sig = sig

        was_upd = self.updatesEnabled()
        self.setUpdatesEnabled(False)
        try:
            while self._v.count():
                item = self._v.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
            t = tokens.get_tokens(self._dark)
            for entry in items or []:
                is_cur = (
                    cur is not None
                    and entry.get("text") == cur.get("text")
                    and entry.get("start") == cur.get("start")
                )
                row = QWidget()
                row.setObjectName("dayRow")
                qss_engine.set_prop(row, "active", "true" if is_cur else "false", polish=False)
                rh = QHBoxLayout(row)
                rh.setContentsMargins(
                    tokens.spx(6, self._scale),
                    tokens.spx(4, self._scale),
                    tokens.spx(6, self._scale),
                    tokens.spx(4, self._scale),
                )
                rh.setSpacing(tokens.spx(8, self._scale))

                dot = ui_parts.PulseStatusDot(t.warn_solid if is_cur else t.text_disabled, self._scale, animated=is_cur)
                rh.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)

                start_s = str(entry.get("start", "")).strip()
                end_s = str(entry.get("end", "")).strip()
                t_range = f"{start_s} - {end_s}" if end_s else start_s
                time_lbl = make_label(
                    t_range, max(9, 11 * self._scale), t.warn if is_cur else t.text_muted,
                    600, mono=True, role="warn" if is_cur else "muted",
                )
                time_lbl.setMinimumWidth(max(82, tokens.spx(96, self._scale)))
                rh.addWidget(time_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

                text_lbl = make_label(
                    str(entry.get("text", "")), max(9, 12 * self._scale),
                    t.text if is_cur else t.text_secondary,
                    600 if is_cur else 400, role="primary" if is_cur else "secondary",
                )
                rh.addWidget(text_lbl, 1, Qt.AlignmentFlag.AlignVCenter)
                self._v.addWidget(row)
        finally:
            self.setUpdatesEnabled(was_upd)


class HeaderSection(TierCard):
    """Hero 日程焦点卡：大标题 + 状态胶囊 + 缓动进度条 + 平滑折叠全天日程抽屉。"""

    heightChanged = Signal()

    def __init__(self, dark: bool, scale: float, parent: QWidget | None = None):
        super().__init__(dark, scale, tokens.RADIUS["card"], parent)
        self._scale = scale
        self._dark = dark
        t = tokens.get_tokens(dark)

        v = QVBoxLayout(self)
        pad_x = tokens.spx(14, scale, lo=10)
        pad_y = tokens.spx(12, scale, lo=8)
        v.setContentsMargins(pad_x, pad_y, pad_x, pad_y)
        v.setSpacing(tokens.spx(7, scale, lo=4))

        top = make_transparent_widget()
        th = QHBoxLayout(top)
        th.setContentsMargins(0, 0, 0, 0)
        th.setSpacing(tokens.spx(8, scale))
        th.addWidget(icons.IconWidget("schedule", t.warn_solid, size=tokens.spx(15, scale)), 0, Qt.AlignmentFlag.AlignVCenter)
        self.title = make_label("AnyBar", 14.5 * scale, t.text, 700, role="primary")
        self.title.setMinimumWidth(0)
        th.addWidget(self.title, 1, Qt.AlignmentFlag.AlignVCenter)
        self.state_chip = Badge("● 进行中", t.ok, t.ok_soft, scale, weight=600, tone="ok")
        th.addWidget(self.state_chip, 0, Qt.AlignmentFlag.AlignVCenter)
        v.addWidget(top)

        self._mid = make_transparent_widget()
        mh = QHBoxLayout(self._mid)
        mh.setContentsMargins(0, 0, 0, 0)
        mh.setSpacing(tokens.spx(8, scale))
        self.chip_time = make_label("", 11.5 * scale, t.text_muted, 500, mono=True, role="muted")
        self.chip_time.setMinimumWidth(0)
        mh.addWidget(self.chip_time, 1, Qt.AlignmentFlag.AlignVCenter)
        self.remain_lbl = make_label("", 11.5 * scale, t.warn, 600, mono=True, role="warn")
        self.remain_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        mh.addWidget(self.remain_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        v.addWidget(self._mid)

        self._bar_color = t.warn_solid
        self.bar = SmoothProgressBar(dark, self._bar_color, scale)
        v.addWidget(self.bar)

        foot = make_transparent_widget()
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(0, 0, 0, 0)
        fh.setSpacing(tokens.spx(6, scale))
        self.next_text = make_label("", 11 * scale, t.text_muted, 500, role="muted")
        self.next_text.setMinimumWidth(0)
        fh.addWidget(self.next_text, 1)
        self.more_btn = make_ghost_link("全部日程 ▾", scale, weight=600, hover_tone="accent")
        fh.addWidget(self.more_btn, 0, Qt.AlignmentFlag.AlignRight)
        v.addWidget(foot)

        drawer_body = make_transparent_widget()
        dv = QVBoxLayout(drawer_body)
        dv.setContentsMargins(0, tokens.spx(4, scale), 0, 0)
        dv.setSpacing(0)
        dv.addWidget(Divider(dark))
        self._day_list = DayList(dark, scale)
        dv.addWidget(self._day_list)

        self._day_drawer = motion.CollapsibleSection(drawer_body, expanded=False, parent=self)
        self._day_drawer.heightChanged.connect(self.heightChanged.emit)
        v.addWidget(self._day_drawer)

    def update_data(self, cur, nxt, frac: float, default_text: str, todo_open: int, remain_text: str) -> None:
        t = tokens.get_tokens(self._dark)
        now_hm = datetime.datetime.now().strftime("%H:%M")
        if cur:
            self.title.setText(str(cur.get("text", "")))
            self.chip_time.setText(f"{cur.get('start', '')} - {cur.get('end', '')}")
            self.state_chip.setText("● 进行中")
            self.state_chip.restyle(t.ok, t.ok_soft, tone="ok")
            apply_label_color(self.remain_lbl, t.warn, role="warn")
            pct = int(round(frac * 100))
            self.remain_lbl.setText(f"{remain_text} · {pct}%")
            self.bar.set_color(self._bar_color if frac < 0.85 else t.ok_solid)
            self.bar.set_ratio(frac)
            self._mid.show()
            self.bar.show()
            if nxt:
                self.next_text.setText(f"▸ 接下来 {nxt.get('start', '')} · {nxt.get('text', '')}")
            else:
                self.next_text.setText("▸ 今日后续无排程")
        else:
            self.title.setText(default_text)
            self.state_chip.setText("○ 空闲")
            self.state_chip.restyle(t.text_secondary, t.surface_elevated, tone="neutral")
            self._mid.hide()
            self.bar.hide()
            if nxt:
                self.next_text.setText(f"{now_hm}  ·  ▸ 接下来 {nxt.get('start', '')} · {nxt.get('text', '')}")
            else:
                self.next_text.setText(f"{now_hm}  ·  今日日程已全部结束")

    def set_bar_color(self, color: str) -> None:
        t = tokens.get_tokens(self._dark)
        c = str(color or "").strip() or t.warn_solid
        if QColor(c).isValid():
            self._bar_color = c

    def set_expanded(self, expanded: bool, schedule_items=None, cur=None, animated: bool = False) -> None:
        self.more_btn.setText("收起日程 ▴" if expanded else "全部日程 ▾")
        if expanded and schedule_items is not None:
            self._day_list.set_schedule(schedule_items, cur)
        self._day_drawer.set_expanded(bool(expanded), animated=animated)


class SchedulePanelCard(BasePanelCard):
    """日程悬浮卡片控制器：高内聚管理 HeaderSection 构建、展开状态与 30s 实时刷新。"""

    card_id = "schedule"
    aliases = ("header",)

    def __init__(self) -> None:
        self.header: HeaderSection | None = None

    def reset(self) -> None:
        self.header = None

    def build(self, ctx: PanelCardContext) -> QWidget:
        t = tokens.get_tokens(ctx.dark)
        now = datetime.datetime.now()
        cur = config_mod.current_schedule(ctx.cfg, now)
        nxt, _ = config_mod.next_schedule(ctx.cfg, now)
        frac = config_mod.schedule_progress(ctx.cfg, now)
        todos = ctx.panel._valid_todos()
        open_n = sum(1 for _, item in todos if not item.get("done"))

        hdr = HeaderSection(ctx.dark, ctx.scale)
        hdr.set_bar_color((ctx.cfg.get("style") or {}).get("scheduleBarColor", t.warn_solid))
        hdr.more_btn.clicked.connect(ctx.panel._on_expand_day)
        hdr.heightChanged.connect(ctx.panel._fixup_height)
        hdr.set_expanded(ctx.panel._day_expanded, ctx.cfg.get("schedule", []), cur, animated=False)
        hdr.update_data(cur, nxt, frac, ctx.cfg.get("defaultText", "自由时间"), open_n, format_remain_text(frac, cur))
        self.header = hdr
        return hdr

    def refresh_now(self, ctx: PanelCardContext) -> None:
        if self.header is None:
            return
        now = datetime.datetime.now()
        cur = config_mod.current_schedule(ctx.cfg, now)
        nxt, _ = config_mod.next_schedule(ctx.cfg, now)
        frac = config_mod.schedule_progress(ctx.cfg, now)
        todos = ctx.panel._valid_todos()
        open_n = sum(1 for _, item in todos if not item.get("done"))
        self.header.update_data(
            cur, nxt, frac, ctx.cfg.get("defaultText", "自由时间"), open_n, format_remain_text(frac, cur)
        )

    def play_entrance(self) -> None:
        if self.header is not None and getattr(self.header, "bar", None) is not None:
            self.header.bar.play_entrance(delay_ms=45)

    def stop_animations(self) -> None:
        if self.header is not None and getattr(self.header, "bar", None) is not None:
            self.header.bar.stop_entrance()
