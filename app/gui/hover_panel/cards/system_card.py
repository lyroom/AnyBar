"""app/gui/hover_panel/cards/system_card.py — 电脑硬件监控卡片（三圆环仪表 + 实时网速 + 网络进程下钻）"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.gui import widgets as ui_parts
from app.gui.widgets import motion
from app.styles import icons, tokens

from ..primitives import (
    Divider,
    InnerTile,
    ProbeCircularGauge,
    TierCard,
    apply_label_color,
    make_card_header,
    make_label,
    make_transparent_widget,
)
from .base import BasePanelCard, PanelCardContext


class SystemPanelCard(BasePanelCard):
    """硬件资源探针卡片：高内聚管理 CPU/RAM/Disk 三圆环、网速速率、TOP3 进程抽屉与原位秒级刷新。"""

    card_id = "system"
    source_ids = ("system",)

    def __init__(self) -> None:
        self.card: QWidget | None = None
        self.boxes: dict[str, tuple[QLabel, QLabel]] = {}
        self.gauges: dict[str, ProbeCircularGauge] = {}
        self.detail_labels: dict[str, QLabel] = {}
        self.latency_labels: dict[str, QLabel] = {}
        self.speed_lbl: QLabel | None = None
        self.drill_hint: QLabel | None = None
        self.net_proc_drawer: motion.CollapsibleSection | None = None
        self.net_proc_rows: list[tuple[QLabel, QLabel]] = []
        self.drill_expanded: bool = False

    def reset(self) -> None:
        self.card = None
        self.boxes = {}
        self.gauges = {}
        self.detail_labels = {}
        self.latency_labels = {}
        self.speed_lbl = None
        self.drill_hint = None
        self.net_proc_drawer = None
        self.net_proc_rows = []

    def build(self, ctx: PanelCardContext) -> QWidget | None:
        src_cfg = ctx.cfg.get("sources") or {}
        if not src_cfg.get("system", {}).get("enabled", True):
            return None
        sys_tiles = ctx.source_tiles.get("system")
        if not sys_tiles:
            return None

        dark, scale = ctx.dark, ctx.scale
        t = tokens.get_tokens(dark)
        sp = lambda v, lo=1: tokens.spx(v, scale, lo=lo)

        card = TierCard(dark, scale)
        v = QVBoxLayout(card)
        v.setContentsMargins(sp(14, 10), sp(11, 7), sp(14, 10), sp(10, 7))
        v.setSpacing(sp(8, 5))

        live_pill = make_transparent_widget()
        lh = QHBoxLayout(live_pill)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.setSpacing(sp(5, 3))
        lh.addWidget(ui_parts.PulseStatusDot(t.ok_solid, scale, animated=True), 0, Qt.AlignmentFlag.AlignVCenter)
        lh.addWidget(make_label("实时监控", 11 * scale, t.text_muted, 500, role="muted"), 0, Qt.AlignmentFlag.AlignVCenter)
        v.addWidget(make_card_header("cpu", t.accent, "电脑硬件资源", live_pill, dark, scale))

        dials_row = make_transparent_widget()
        dh = QHBoxLayout(dials_row)
        dh.setContentsMargins(0, sp(3, 2), 0, sp(3, 2))
        dh.setSpacing(sp(8, 6))

        self.card = card
        self.boxes = {}
        self.gauges = {}

        for st in sys_tiles:
            name = str(st.get("name", ""))
            col = make_transparent_widget()
            cv = QVBoxLayout(col)
            cv.setContentsMargins(0, 0, 0, 0)
            cv.setSpacing(sp(3, 2))

            gauge = ProbeCircularGauge(
                ratio=float(st.get("ratio", 0.0)),
                center_text=str(st.get("center_text", "")),
                color=st.get("color"),
                dark=dark,
                scale=scale,
            )
            cv.addWidget(gauge, 0, Qt.AlignmentFlag.AlignHCenter)
            cv.addWidget(make_label(name, 11.5 * scale, t.text, 700, role="primary"), 0, Qt.AlignmentFlag.AlignHCenter)
            detail_text = str(
                st.get("disk_detail") if name == "Disk"
                else (st.get("mem_detail") if name == "RAM" else st.get("sub_text", ""))
            )
            sub_lbl = make_label(detail_text, 10 * scale, t.text_muted, 500, mono=True, role="muted")
            cv.addWidget(sub_lbl, 0, Qt.AlignmentFlag.AlignHCenter)
            dh.addWidget(col, 1)

            self.boxes[name] = (gauge.val_lbl, sub_lbl)
            self.gauges[name] = gauge

        v.addWidget(dials_row)
        v.addWidget(Divider(dark))

        t0 = sys_tiles[0] if sys_tiles else {}
        up_s = t0.get("net_up_str") or "-- B/s"
        down_s = t0.get("net_down_str") or "-- B/s"

        speed_row = InnerTile(dark, scale, interactive=True)
        speed_row.setObjectName("speedRow")
        speed_row.setToolTip("点击展开/折叠 TOP 3 活跃网络进程排查（下钻）")
        sh = QHBoxLayout(speed_row)
        sh.setContentsMargins(sp(9, 6), sp(6, 4), sp(9, 6), sp(6, 4))
        sh.setSpacing(sp(6, 4))
        sh.addWidget(icons.IconWidget("network", t.accent, size=sp(13, 11)), 0, Qt.AlignmentFlag.AlignVCenter)
        sh.addWidget(make_label("网络速率", 11 * scale, t.text_secondary, 500, role="secondary"), 0)
        self.drill_hint = make_label("排查 ▾", 10 * scale, t.warn, 600, role="warn")
        sh.addWidget(self.drill_hint, 0)
        sh.addStretch(1)
        self.speed_lbl = make_label(f"↑ {up_s}   ↓ {down_s}", 11 * scale, t.text, 600, mono=True, role="primary")
        sh.addWidget(self.speed_lbl, 0)
        v.addWidget(speed_row)

        net_box = InnerTile(dark, scale, interactive=False)
        net_box.setObjectName("netProcBox")
        np_v = QVBoxLayout(net_box)
        np_v.setContentsMargins(sp(10, 6), sp(7, 4), sp(10, 6), sp(7, 5))
        np_v.setSpacing(sp(4, 2))
        np_v.addWidget(make_label("TCP 活跃连接 TOP 3 进程", 10.5 * scale, t.warn, 600, role="warn"))

        self.net_proc_rows = []
        for _ in range(3):
            p_row = make_transparent_widget()
            p_h = QHBoxLayout(p_row)
            p_h.setContentsMargins(0, 0, 0, 0)
            name_l = make_label("--", 11 * scale, t.text, 500, role="primary")
            cnt_l = make_label("--", 10.5 * scale, t.text_muted, 600, mono=True, role="muted")
            p_h.addWidget(name_l, 1)
            p_h.addWidget(cnt_l, 0)
            np_v.addWidget(p_row)
            self.net_proc_rows.append((name_l, cnt_l))

        self.net_proc_drawer = motion.CollapsibleSection(net_box, expanded=self.drill_expanded, parent=card)
        self.net_proc_drawer.heightChanged.connect(ctx.panel._fixup_height)
        v.addWidget(self.net_proc_drawer)

        def _toggle_net_drill():
            self.drill_expanded = not bool(self.drill_expanded)
            cur_tiles = ctx.panel._source_tiles.get("system") or []
            self.update_net_proc_drilldown(cur_tiles[0] if cur_tiles else {}, force_query=True, animated=True)

        speed_row.clicked.connect(_toggle_net_drill)
        self.update_net_proc_drilldown(t0, animated=False)

        self.detail_labels = {"speed": self.speed_lbl}
        self.latency_labels = {}
        return card

    def update_net_proc_drilldown(self, t0: dict, force_query: bool = False, animated: bool = False) -> None:
        if self.net_proc_drawer is None:
            return
        is_expanded = bool(self.drill_expanded)
        if self.drill_hint is not None:
            self.drill_hint.setText("排查 ▴" if is_expanded else "排查 ▾")

        if is_expanded:
            procs = t0.get("top_net_procs")
            if not procs or force_query:
                try:
                    from app.core.sources.system_source import get_top_network_processes
                    procs = get_top_network_processes(3)
                except Exception:
                    procs = []

            for i in range(3):
                if i < len(self.net_proc_rows):
                    nl, cl = self.net_proc_rows[i]
                    if procs and i < len(procs):
                        item = procs[i]
                        nl.setText(f"• {item.get('name') or '未知进程'}")
                        cl.setText(f"{item.get('connections', 0)} 连接")
                        nl.parentWidget().show()
                    elif i == 0 and not procs:
                        nl.setText("• 暂无高频活跃连接进程")
                        cl.setText("")
                        nl.parentWidget().show()
                    else:
                        nl.parentWidget().hide()

        self.net_proc_drawer.set_expanded(is_expanded, animated=animated)

    def try_update_inplace(self, source_id: str, ctx: PanelCardContext) -> bool:
        if source_id != "system":
            return False
        if self.card is None or not self.boxes or self.card.parent() is None:
            return False
        sys_tiles = ctx.source_tiles.get("system") or []
        new_names = [str(x.get("name", "")) for x in sys_tiles]
        if list(self.boxes.keys()) != new_names:
            return False

        for tile in sys_tiles:
            name = str(tile.get("name", ""))
            if name in self.boxes:
                val_lbl, sub_lbl = self.boxes[name]
                c_txt = str(tile.get("center_text", ""))
                if val_lbl.text() != c_txt:
                    val_lbl.setText(c_txt)
                c = tile.get("color")
                if c and val_lbl.property("_lastColor") != c:
                    val_lbl.setProperty("_lastColor", c)
                    apply_label_color(val_lbl, str(c))
                dt = str(
                    tile.get("disk_detail") if name == "Disk"
                    else (tile.get("mem_detail") if name == "RAM" else tile.get("sub_text", ""))
                )
                if sub_lbl.text() != dt:
                    sub_lbl.setText(dt)
                if name in self.gauges:
                    self.gauges[name].set_gauge_value(float(tile.get("ratio", 0.0)), c_txt, c)

        t0 = sys_tiles[0] if sys_tiles else {}
        up_s = t0.get("net_up_str") or "-- B/s"
        down_s = t0.get("net_down_str") or "-- B/s"
        speed_text = f"↑ {up_s}   ↓ {down_s}"
        if "speed" in self.detail_labels and self.detail_labels["speed"].text() != speed_text:
            self.detail_labels["speed"].setText(speed_text)
        if self.speed_lbl is not None and self.speed_lbl.text() != speed_text:
            self.speed_lbl.setText(speed_text)
        if self.drill_expanded:
            self.update_net_proc_drilldown(t0, animated=False)
        return True

    def play_entrance(self) -> None:
        for idx, gauge in enumerate(self.gauges.values()):
            gauge.play_entrance(delay_ms=55 + idx * 70)

    def stop_animations(self) -> None:
        for gauge in self.gauges.values():
            gauge.stop_entrance()
