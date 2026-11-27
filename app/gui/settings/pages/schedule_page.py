"""app/gui/settings/pages/schedule_page.py — 设置中心「日程时段」页"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.gui import widgets as ui_parts

from ..form_helpers import SettingsFormContext, normalize_time_str, set_edit_text
from .base import BaseSettingsPage


class SchedulePage(BaseSettingsPage):
    """日程时段列表 + 非时段默认提醒文字配置页。"""

    page_id = "schedule"
    title = "日程时段"

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []
        self._list_box: QVBoxLayout | None = None
        self.default_edit: QLineEdit | None = None

    def build(self, ctx: SettingsFormContext) -> QWidget:
        self._ctx = ctx
        self.rows = []
        m = ctx.metrics
        page, lay = ctx.make_page()

        lay.addWidget(ctx.make_col_header([
            ("开始", m.time_w, 0, Qt.AlignmentFlag.AlignCenter),
            ("结束", m.time_w, 0, Qt.AlignmentFlag.AlignCenter),
            ("时段提醒文本", None, 3),
            ("备注说明", None, 2),
            ("删除", m.del_w, 0, Qt.AlignmentFlag.AlignCenter),
        ]))

        scroll, self._list_box = ctx.make_row_scroll()
        lay.addWidget(scroll, 1)
        lay.addWidget(ctx.make_add_btn("+ 添加日程时段", lambda: self.add_row({})))

        default_edit = QLineEdit()
        default_edit.setFixedHeight(m.edit_h)
        default_edit.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.default_edit = default_edit

        default_group = ui_parts.SettingGroupCard(ctx.dark, ctx.scale)
        default_row = QWidget()
        default_row.setObjectName("defaultRow")
        dh = QHBoxLayout(default_row)
        dh.setContentsMargins(0, ctx.px(4), 0, ctx.px(4))
        dh.setSpacing(ctx.px(14))
        dh.addWidget(QLabel("非时段提示文字"))
        dh.addWidget(default_edit, 1)
        default_group.add_row(default_row)
        lay.addWidget(default_group)

        lay.addWidget(ctx.make_tip(
            "时段按开始时间排序生效；跨零点时段自动按夜间计算。",
            icon_name="info",
        ))
        return page

    def add_row(self, item: dict[str, Any] | None = None) -> dict[str, Any]:
        assert self._ctx is not None and self._list_box is not None
        ctx = self._ctx
        m = ctx.metrics
        item = item or {}

        start = ctx.make_time_edit(str(item.get("start", "08:00")), allow_empty=False, default_str="08:00")
        end = ctx.make_time_edit(str(item.get("end", "12:00")), allow_empty=False, default_str="12:00")

        text = QLineEdit(item.get("text", ""))
        text.setCursorPosition(0)
        text.setPlaceholderText("提醒文字")
        text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        text.setFixedHeight(m.edit_h)

        note = QLineEdit(item.get("note", ""))
        note.setCursorPosition(0)
        note.setPlaceholderText("备注（可选）")
        note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        note.setFixedHeight(m.edit_h)

        entry: dict[str, Any] = {"start": start, "end": end, "text": text, "note": note}
        card, h = ctx.make_row_card()
        h.addWidget(start)
        h.addWidget(end)
        h.addWidget(text, 3)
        h.addWidget(note, 2)
        trash = ctx.make_del_btn(
            lambda _checked=False, e=entry: ctx.remove_row(self.rows, e, self._list_box)
        )
        h.addWidget(trash)

        entry["card"] = card
        self.rows.append(entry)
        self._list_box.insertWidget(self._list_box.count() - 1, card)
        for w in (text, note):
            w.textChanged.connect(ctx.schedule_preview)
        return entry

    def load(self, cfg: dict[str, Any]) -> None:
        if self._list_box is None or self.default_edit is None:
            return
        for entry in list(self.rows):
            self._list_box.removeWidget(entry["card"])
            entry["card"].deleteLater()
        self.rows = []
        for item in cfg.get("schedule", []) or []:
            self.add_row(item)
        set_edit_text(self.default_edit, cfg.get("defaultText", ""))

    def collect(self, cfg: dict[str, Any]) -> None:
        schedule = []
        for e in self.rows:
            text = e["text"].text().strip()
            if not text:
                continue
            schedule.append({
                "start": normalize_time_str(e["start"].text(), allow_empty=False, default_str="08:00"),
                "end": normalize_time_str(e["end"].text(), allow_empty=False, default_str="12:00"),
                "text": text,
                "note": e["note"].text().strip(),
            })
        cfg["schedule"] = schedule
        if self.default_edit is not None:
            cfg["defaultText"] = self.default_edit.text().strip() or "自由时间 · 注意休息"

    def connect_preview(self) -> None:
        if self._ctx is not None and self.default_edit is not None:
            self.default_edit.textChanged.connect(self._ctx.schedule_preview)
