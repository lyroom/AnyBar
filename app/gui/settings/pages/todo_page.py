"""app/gui/settings/pages/todo_page.py — 设置中心「待办事项」页"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..form_helpers import SettingsFormContext, normalize_time_str, set_edit_text
from .base import BaseSettingsPage


class TodoPage(BaseSettingsPage):
    """待办事项管理页（含勾选完成状态与悬停面板双向同步）。"""

    page_id = "todos"
    title = "待办事项"

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []
        self._list_box: QVBoxLayout | None = None

    def build(self, ctx: SettingsFormContext) -> QWidget:
        self._ctx = ctx
        self.rows = []
        m = ctx.metrics
        page, lay = ctx.make_page()

        lay.addWidget(ctx.make_col_header([
            ("完成", m.cb_col_w, 0, Qt.AlignmentFlag.AlignCenter),
            ("时间", m.time_w, 0, Qt.AlignmentFlag.AlignCenter),
            ("待办事项内容", None, 2),
            ("备注", None, 1),
            ("删除", m.del_w, 0, Qt.AlignmentFlag.AlignCenter),
        ]))

        scroll, self._list_box = ctx.make_row_scroll()
        lay.addWidget(scroll, 1)
        lay.addWidget(ctx.make_add_btn("+ 添加待办事项", self.add_row))
        lay.addWidget(ctx.make_tip(
            "时间设为 --:-- 表示不显示时间；标题将显示在任务栏滚动行中，完成后自动隐藏。",
            icon_name="info",
        ))
        return page

    def add_row(self) -> dict[str, Any]:
        assert self._ctx is not None and self._list_box is not None
        ctx = self._ctx
        m = ctx.metrics

        time_edit = ctx.make_time_edit("", allow_empty=True, default_str="")

        title = QLineEdit("")
        title.setPlaceholderText("待办标题")
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        title.setFixedHeight(m.edit_h)

        note = QLineEdit("")
        note.setPlaceholderText("备注（可选）")
        note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        note.setFixedHeight(m.edit_h)

        done = QCheckBox()
        done.setObjectName("todoDoneCheck")

        done_box = QWidget()
        done_box.setObjectName("doneBox")
        done_box.setFixedWidth(m.cb_col_w)
        db = QHBoxLayout(done_box)
        db.setContentsMargins(0, 0, 0, 0)
        db.setSpacing(0)
        db.addWidget(done, 0, Qt.AlignmentFlag.AlignCenter)

        entry: dict[str, Any] = {"time": time_edit, "title": title, "note": note, "done": done}
        card, h = ctx.make_row_card()
        h.addWidget(done_box)
        h.addWidget(time_edit)
        h.addWidget(title, 2)
        h.addWidget(note, 1)
        trash = ctx.make_del_btn(
            lambda _checked=False, e=entry: ctx.remove_row(self.rows, e, self._list_box)
        )
        h.addWidget(trash)

        entry["card"] = card
        self.rows.append(entry)
        self._list_box.insertWidget(self._list_box.count() - 1, card)
        title.textChanged.connect(ctx.schedule_preview)
        note.textChanged.connect(ctx.schedule_preview)
        done.toggled.connect(ctx.schedule_preview)
        return entry

    def load(self, cfg: dict[str, Any]) -> None:
        if self._list_box is None:
            return
        for entry in list(self.rows):
            self._list_box.removeWidget(entry["card"])
            entry["card"].deleteLater()
        self.rows = []
        for item in cfg.get("todos", []) or []:
            entry = self.add_row()
            raw_time = str(item.get("time", "") or "").strip()
            if raw_time == "--:--":
                raw_time = ""
            set_edit_text(entry["time"], raw_time)
            entry["time"].setPlaceholderText("--:--")
            set_edit_text(entry["title"], item.get("title", ""))
            set_edit_text(entry["note"], item.get("note", ""))
            entry["done"].setChecked(bool(item.get("done", False)))

    def collect(self, cfg: dict[str, Any]) -> None:
        todos = []
        for e in self.rows:
            title = e["title"].text().strip()
            if not title:
                continue
            todos.append({
                "time": normalize_time_str(e["time"].text(), allow_empty=True, default_str=""),
                "title": title,
                "note": e["note"].text().strip(),
                "done": e["done"].isChecked(),
            })
        cfg["todos"] = todos

    def sync_done_state(self, live_cfg: dict[str, Any] | None, local_cfg: dict[str, Any]) -> None:
        if not isinstance(live_cfg, dict):
            return
        live_todos = live_cfg.get("todos", []) or []
        local_todos = local_cfg.get("todos", []) or []
        if len(live_todos) != len(local_todos) or len(live_todos) != len(self.rows):
            return
        for dst, src in zip(local_todos, live_todos):
            if isinstance(dst, dict) and isinstance(src, dict):
                dst["done"] = bool(src.get("done", False))
        for entry, item in zip(self.rows, local_todos):
            entry["done"].setChecked(bool(item.get("done", False)))
