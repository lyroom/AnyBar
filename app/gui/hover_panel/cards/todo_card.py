"""app/gui/hover_panel/cards/todo_card.py — 待办事项卡片（打勾弹跳 + 划除动画 + 已完成折叠抽屉）"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.gui.widgets import motion
from app.styles import qss_engine, tokens

from ..primitives import (
    Badge,
    TierCard,
    apply_label_color,
    make_card_header,
    make_ghost_link,
    make_label,
    make_transparent_widget,
    ui_font,
)
from .base import BasePanelCard, PanelCardContext


class AppleCheckCircle(QWidget):
    """自绘矢量圆形复选控件：悬停颜色补间 + OutBack 勾选弹跳动画。"""

    toggled = Signal(bool)

    def __init__(self, scale: float, dark: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._scale = max(1.0, float(scale))
        self._dark = bool(dark)
        self._checked = False
        self._check_scale = 1.0
        self._anim: QPropertyAnimation | None = None
        self._hover_tween = motion.ValueTween(0.0, tokens.MOTION["micro"], parent=self)
        self._hover_tween.changed.connect(lambda _v: self.update())

        d = max(18, tokens.spx(22, self._scale))
        self.setFixedSize(d, d)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def get_check_scale(self) -> float:
        return self._check_scale

    def set_check_scale(self, val: float) -> None:
        self._check_scale = float(val)
        self.update()

    checkScale = Property(float, get_check_scale, set_check_scale)

    def set_checked(self, checked: bool) -> None:
        if bool(checked) != self._checked:
            self._checked = bool(checked)
            self._check_scale = 1.0
            self.update()

    def enterEvent(self, event):
        self._hover_tween.animate_to(1.0, animate=self.isVisible())
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_tween.animate_to(0.0, animate=self.isVisible())
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            if self._checked:
                if self._anim is not None:
                    self._anim.stop()
                    self._anim.deleteLater()
                self._anim = QPropertyAnimation(self, b"checkScale", self)
                self._anim.setDuration(tokens.MOTION["emphasis"])
                self._anim.setStartValue(0.32)
                self._anim.setEndValue(1.0)
                self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
                self._anim.start()
            else:
                self._check_scale = 1.0
            self.update()
            self.toggled.emit(self._checked)

    def paintEvent(self, event):
        t = tokens.get_tokens(self._dark)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        r = max(3.5, 6.8 * self._scale)
        hv = self._hover_tween.value
        accent = QColor(t.accent)

        if not self._checked:
            ring_col = motion.blend_color(QColor(t.border_strong), accent, hv)
            fill_col = motion.blend_color(QColor(t.surface_sunken), QColor(t.accent), hv * 0.16)
            p.setPen(QPen(ring_col, max(1.2, 1.55 * self._scale)))
            p.setBrush(fill_col)
            p.drawEllipse(QPointF(cx, cy), r, r)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(motion.blend_color(accent, QColor(t.accent_hover), hv * 0.5))
            p.drawEllipse(QPointF(cx, cy), r, r)
            pen = QPen(QColor(t.text_on_accent), max(1.2, 1.6 * self._scale))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.save()
            p.translate(cx, cy)
            p.scale(self._check_scale, self._check_scale)
            p.translate(-cx, -cy)
            p.drawPolyline([
                QPointF(cx - r * 0.36, cy + r * 0.02),
                QPointF(cx - r * 0.08, cy + r * 0.32),
                QPointF(cx + r * 0.40, cy - r * 0.28),
            ])
            p.restore()
        p.end()


class TodoRow(QFrame):
    """待办单行：平滑悬停表面提亮 + OutBack 划除线动画 + 内缩细分割线（样式由 hover_panel.qss 驱动）。"""

    toggled = Signal(int, bool)

    def __init__(self, index: int, todo: dict, dark: bool, scale: float,
                 show_separator: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self._index = index
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self._done = bool(todo.get("done"))
        self._sep = bool(show_separator)
        self._strike_progress = 1.0 if self._done else 0.0
        self._strike_anim: QPropertyAnimation | None = None
        self._hover_tween = motion.ValueTween(0.0, tokens.MOTION["micro"], parent=self)
        self._hover_tween.changed.connect(lambda _v: self.update())

        self.setObjectName("todoRow")
        t = tokens.get_tokens(self._dark)

        h = QHBoxLayout(self)
        h.setContentsMargins(self._px(6), self._px(5), self._px(6), self._px(5))
        h.setSpacing(self._px(7))

        self.check = AppleCheckCircle(scale, dark)
        self.check.set_checked(self._done)
        self.check.toggled.connect(self._on_toggle)
        h.addWidget(self.check, 0, Qt.AlignmentFlag.AlignTop)

        self.text = make_label("", 12.5 * scale, t.text, 400, wrap=True, role="primary")
        self.text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        h.addWidget(self.text, 1)

        self.time_lbl = QLabel("")
        self.time_lbl.setObjectName("todoTimePill")
        self.time_lbl.setFont(ui_font(10.5 * scale, 600, mono=True))
        h.addWidget(self.time_lbl, 0, Qt.AlignmentFlag.AlignTop)

        self.set_todo(todo)

    def get_strike_progress(self) -> float:
        return self._strike_progress

    def set_strike_progress(self, val: float) -> None:
        self._strike_progress = float(val)
        self.update()

    strikeProgress = Property(float, get_strike_progress, set_strike_progress)

    def _px(self, v: float) -> int:
        return tokens.spx(v, self._scale)

    def enterEvent(self, event):
        self._hover_tween.animate_to(1.0, animate=self.isVisible())
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_tween.animate_to(0.0, animate=self.isVisible())
        super().leaveEvent(event)

    def set_todo(self, todo: dict) -> None:
        self._plain = str(todo.get("title", "")).strip()
        self._done = bool(todo.get("done"))
        self._strike_progress = 1.0 if self._done else 0.0
        self._paint_text()
        self._time = str(todo.get("time", "")).strip()
        self._paint_time()

    def _paint_text(self) -> None:
        t = tokens.get_tokens(self._dark)
        self.text.setText(self._plain)
        self.text.setFont(ui_font(12.5 * self._scale, 400))
        apply_label_color(self.text, t.text_muted if self._done else t.text, role="muted" if self._done else "primary")

    def _paint_time(self) -> None:
        if not self._time or self._time == "--:--":
            self.time_lbl.hide()
            return
        self.time_lbl.show()
        self.time_lbl.setText(self._time)
        qss_engine.set_prop(self.time_lbl, "done", "true" if self._done else "false")

    def _on_toggle(self, checked: bool) -> None:
        self._done = bool(checked)
        if self._strike_anim is not None:
            self._strike_anim.stop()
            self._strike_anim.deleteLater()
            self._strike_anim = None
        if self._done:
            self._strike_anim = QPropertyAnimation(self, b"strikeProgress", self)
            self._strike_anim.setDuration(tokens.MOTION["emphasis"])
            self._strike_anim.setStartValue(0.0)
            self._strike_anim.setEndValue(1.0)
            self._strike_anim.setEasingCurve(QEasingCurve.Type.OutBack)
            self._strike_anim.start()
        else:
            self._strike_progress = 0.0
            self.update()
        self._paint_text()
        self._paint_time()
        self.toggled.emit(self._index, self._done)

    def paintEvent(self, event):
        t = tokens.get_tokens(self._dark)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        hv = self._hover_tween.value
        if hv > 0.005:
            hc = QColor(t.surface_hover)
            hc.setAlpha(int(round(215 * hv)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(hc)
            rad = float(self._px(7))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -1.5), rad, rad)

        if self._done and self._strike_progress > 0:
            pen = QPen(QColor(t.text_muted), max(1.2, 1.4 * self._scale))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            t_geo = self.text.geometry()
            tx = float(t_geo.left())
            ty = float(t_geo.top()) + t_geo.height() / 2.0
            fm = self.text.fontMetrics()
            tw = min(float(fm.horizontalAdvance(self._plain) + 4), float(t_geo.width()))
            line_w = tw * min(1.0, max(0.0, self._strike_progress))
            p.drawLine(QPointF(tx, ty), QPointF(tx + line_w, ty))

        if self._sep:
            p.setPen(QColor(*t.divider_rgba))
            y = self.height() - 1
            p.drawLine(self._px(34), y, self.width() - self._px(6), y)
        p.end()


class TodoPanelCard(BasePanelCard):
    """待办事项卡片控制器：封装待办列表构建、已完成抽屉与原位增量刷新。"""

    card_id = "todos"

    def __init__(self) -> None:
        self.card: QWidget | None = None
        self.items_host: QWidget | None = None
        self.items_lay: QVBoxLayout | None = None
        self.count_badge: Badge | None = None
        self.done_drawer: motion.CollapsibleSection | None = None
        self.done_toggle_btn: QPushButton | None = None
        self.done_clear_btn: QPushButton | None = None
        self.rows: dict[int, TodoRow] = {}

    def reset(self) -> None:
        self.card = None
        self.items_host = None
        self.items_lay = None
        self.count_badge = None
        self.done_drawer = None
        self.done_toggle_btn = None
        self.done_clear_btn = None
        self.rows = {}

    def build(self, ctx: PanelCardContext) -> QWidget:
        dark, scale = ctx.dark, ctx.scale
        t = tokens.get_tokens(dark)
        sp = lambda v, lo=1: tokens.spx(v, scale, lo=lo)
        todos = ctx.panel._valid_todos()

        card = TierCard(dark, scale)
        v = QVBoxLayout(card)
        v.setContentsMargins(sp(14, 10), sp(11, 7), sp(14, 10), sp(11, 7))
        v.setSpacing(sp(6, 4))

        done_n = sum(1 for _, item in todos if item.get("done"))
        self.count_badge = Badge(f"已完成 {done_n}/{len(todos)}", t.ok, t.ok_soft, scale, weight=600, tone="ok")
        v.addWidget(make_card_header("todo", t.accent, "待办事项", self.count_badge, dark, scale))

        items_host = make_transparent_widget(card)
        items_lay = QVBoxLayout(items_host)
        items_lay.setContentsMargins(0, 0, 0, 0)
        items_lay.setSpacing(sp(4, 2))
        v.addWidget(items_host)

        self.card = card
        self.items_host = items_host
        self.items_lay = items_lay
        self.populate_items(ctx.panel, dark, scale, todos)

        v.addWidget(ctx.panel._add_input)
        return card

    def populate_items(self, panel, dark: bool, scale: float, todos) -> None:
        if self.items_lay is None or self.card is None:
            return
        t = tokens.get_tokens(dark)
        sp = lambda v, lo=1: tokens.spx(v, scale, lo=lo)

        panel._clear_layout(self.items_lay)
        self.done_drawer = None
        self.rows = {}

        done_n = sum(1 for _, item in todos if item.get("done"))
        if self.count_badge is not None:
            self.count_badge.setText(f"已完成 {done_n}/{len(todos)}")

        active = [(o, item) for o, item in todos if not item.get("done")]
        finished = [(o, item) for o, item in todos if item.get("done")]

        if active:
            n = len(active)
            for pos, (orig, item) in enumerate(active):
                row = TodoRow(orig, item, dark, scale, show_separator=pos < n - 1)
                row.toggled.connect(panel._on_todo_check)
                self.rows[pos] = row
                self.items_lay.addWidget(row)
        elif finished:
            hint = make_label("今日待办已全部完成", 12 * scale, t.ok, 600, role="ok")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setContentsMargins(sp(8), sp(8), sp(8), sp(8))
            self.items_lay.addWidget(hint)
        else:
            empty = make_label("暂无待办 · 下方输入回车快速添加", 11.5 * scale, t.text_muted, 500, role="muted")
            empty.setContentsMargins(sp(4), sp(2), sp(4), sp(2))
            self.items_lay.addWidget(empty)

        if finished:
            if panel._done_expanded is None:
                panel._done_expanded = False
            self.items_lay.addWidget(self._build_done_header(panel, scale, len(finished)))
            done_container = make_transparent_widget()
            dv = QVBoxLayout(done_container)
            dv.setContentsMargins(0, 0, 0, 0)
            dv.setSpacing(0)
            m = len(finished)
            for pos, (orig, item) in enumerate(finished):
                row = TodoRow(orig, item, dark, scale, show_separator=pos < m - 1)
                row.toggled.connect(panel._on_todo_check)
                self.rows[len(self.rows)] = row
                dv.addWidget(row)
            self.done_drawer = motion.CollapsibleSection(
                done_container, expanded=bool(panel._done_expanded), parent=self.card
            )
            self.done_drawer.heightChanged.connect(panel._fixup_height)
            self.items_lay.addWidget(self.done_drawer)

    def _build_done_header(self, panel, scale: float, done_count: int) -> QWidget:
        sp = lambda v: tokens.spx(v, scale)
        head = make_transparent_widget()
        h = QHBoxLayout(head)
        h.setContentsMargins(sp(2), 0, sp(2), 0)
        h.setSpacing(sp(4))
        head.setFixedHeight(sp(26))

        arrow = "▾" if panel._done_expanded else "▸"
        self.done_toggle_btn = make_ghost_link(f"{arrow} 已完成 ({done_count})", scale, weight=600, hover_tone="accent")
        self.done_toggle_btn.clicked.connect(panel._on_toggle_done_section)
        h.addWidget(self.done_toggle_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        h.addStretch(1)

        self.done_clear_btn = make_ghost_link("清除已完成", scale, weight=500, hover_tone="danger")
        self.done_clear_btn.clicked.connect(panel._on_clear_done)
        h.addWidget(self.done_clear_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        return head
