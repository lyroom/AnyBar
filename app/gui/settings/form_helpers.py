"""app/gui/settings/form_helpers.py — 设置中心共享布局度量、时间规范化与控件工厂"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.gui import widgets as ui_parts
from app.styles import icons, qss_engine, theme, tokens


def normalize_time_str(raw: str, allow_empty: bool = False, default_str: str = "08:00") -> str:
    """将用户输入的时间文本规范化为 HH:MM（兼容全角冒号与纯数字简写）。"""
    s = str(raw or "").strip().replace("：", ":")
    if not s or s == "--:--":
        return "" if allow_empty else default_str
    if s.isdigit():
        if len(s) <= 2:
            h = max(0, min(23, int(s)))
            return f"{h:02d}:00"
        if len(s) == 3:
            h = max(0, min(23, int(s[0])))
            m = max(0, min(59, int(s[1:])))
            return f"{h:02d}:{m:02d}"
        if len(s) >= 4:
            h = max(0, min(23, int(s[:2])))
            m = max(0, min(59, int(s[2:4])))
            return f"{h:02d}:{m:02d}"
    if ":" in s:
        parts = s.split(":", 1)
        p0, p1 = parts[0].strip(), parts[1].strip()
        if p0.isdigit() and p1.isdigit():
            h = max(0, min(23, int(p0)))
            m = max(0, min(59, int(p1)))
            return f"{h:02d}:{m:02d}"
        if p0.isdigit() and not p1:
            h = max(0, min(23, int(p0)))
            return f"{h:02d}:00"
    return s


def fmt_quota_num(v) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        fv = float(v)
        if abs(fv) >= 100 or abs(fv - round(fv)) < 0.05:
            return str(int(round(fv)))
        return f"{round(fv, 1):g}"
    return str(v)


def set_edit_text(edit: QLineEdit, text: str) -> None:
    edit.setText(text)
    edit.setCursorPosition(0)


@dataclass
class SettingsMetrics:
    scale: float
    cb_ind: int
    time_w: int
    quota_prov_w: int
    quota_val_w: int
    quota_name_w: int
    quota_key_min_w: int
    num_w: int
    unit_w: int
    cb_col_w: int
    combo_min_w: int
    slider_w: int
    row_h: int
    panel_row_h: int
    edit_h: int
    btn_h: int
    col_h: int
    del_w: int
    handle_w: int
    color_h: int
    save_btn_w: int
    btn_min_w: int
    add_btn_h: int
    seg_h: int

    @classmethod
    def from_scale(cls, scale: float) -> "SettingsMetrics":
        px = lambda v: tokens.spx(v, scale)
        return cls(
            scale=scale,
            cb_ind=px(18),
            time_w=px(70),
            quota_prov_w=px(102),
            quota_val_w=px(62),
            quota_name_w=px(88),
            quota_key_min_w=px(100),
            num_w=px(66),
            unit_w=px(44),
            cb_col_w=px(44),
            combo_min_w=px(156),
            slider_w=px(156),
            row_h=px(46),
            panel_row_h=px(58),
            edit_h=px(31),
            btn_h=px(35),
            col_h=px(24),
            del_w=px(28),
            handle_w=px(20),
            color_h=px(30),
            save_btn_w=px(102),
            btn_min_w=px(78),
            add_btn_h=px(36),
            seg_h=px(38),
        )


class SettingsFormContext:
    """设置页面共享构建上下文：封装主题、DPI 度量与零内联 QSS 的标准控件工厂。"""

    def __init__(
        self,
        dialog: QWidget,
        dark: bool,
        scale: float,
        schedule_preview: Callable[[], None],
        trigger_preview: Callable[[], None],
        show_toast: Callable[[str, str], None],
    ) -> None:
        self.dialog = dialog
        self.dark = bool(dark)
        self.scale = float(scale)
        self.metrics = SettingsMetrics.from_scale(self.scale)
        self.schedule_preview = schedule_preview
        self.trigger_preview = trigger_preview
        self.show_toast = show_toast

    def px(self, base_px: float) -> int:
        return tokens.spx(base_px, self.scale)

    def make_action_btn(self, text: str, icon_name: str = "", primary: bool = False, ghost: bool = False) -> QPushButton:
        t = tokens.get_tokens(self.dark)
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoDefault(False)
        btn.setDefault(False)
        if primary:
            btn.setObjectName("primaryBtn")
        elif ghost:
            btn.setObjectName("ghostBtn")
        if icon_name:
            ic_color = t.text_on_accent if primary else t.icon
            ic_sz = self.px(14)
            btn.setIcon(icons.make_qicon(icon_name, ic_color, size=ic_sz))
            btn.setIconSize(QSize(ic_sz, ic_sz))
        return btn

    def make_page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("pageRoot")
        page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(self.px(2), self.px(2), self.px(2), self.px(2))
        lay.setSpacing(self.px(10))
        return page, lay

    def make_scroll_page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("pageRoot")
        page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("pageInner")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(self.px(2), self.px(2), self.px(6), self.px(4))
        lay.setSpacing(self.px(10))
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return page, lay

    def make_row_scroll(self) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setObjectName("rowsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(self.px(80))
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        inner = QWidget()
        inner.setObjectName("rowsInner")
        box = QVBoxLayout(inner)
        box.setContentsMargins(0, 0, self.px(4), 0)
        box.setSpacing(self.px(6))
        box.addStretch(1)
        scroll.setWidget(inner)
        return scroll, box

    def make_col_header(self, specs) -> QWidget:
        row = QWidget()
        row.setObjectName("colHeaderRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(self.px(12), 0, self.px(12), 0)
        h.setSpacing(self.px(8))
        f = theme.ui_font(11.5 * self.scale, 600)
        for spec in specs:
            text, width, stretch = spec[0], spec[1], spec[2]
            align = spec[3] if len(spec) > 3 else Qt.AlignmentFlag.AlignLeft
            min_w = spec[4] if len(spec) > 4 else None
            lbl = QLabel(text)
            lbl.setObjectName("colHeader")
            lbl.setFont(f)
            lbl.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
            if width:
                lbl.setFixedWidth(width)
                h.addWidget(lbl)
            else:
                lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                lbl.setContentsMargins(self.px(4), 0, 0, 0)
                if min_w is not None:
                    lbl.setMinimumWidth(min_w)
                h.addWidget(lbl, stretch)
        row.setFixedHeight(self.metrics.col_h)
        return row

    def make_row_card(self, height: int | None = None) -> tuple[QFrame, QHBoxLayout]:
        card = QFrame()
        card.setObjectName("RowCard")
        card.setFixedHeight(self.metrics.row_h if height is None else height)
        h = QHBoxLayout(card)
        h.setContentsMargins(self.px(12), self.px(6), self.px(12), self.px(6))
        h.setSpacing(self.px(8))
        return card, h

    def make_time_edit(self, text: str = "", allow_empty: bool = False, default_str: str = "08:00") -> QLineEdit:
        init_txt = "" if (not text or text == "--:--") else str(text)
        edit = QLineEdit(init_txt)
        edit.setReadOnly(False)
        edit.setEnabled(True)
        edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        edit.setFont(theme.ui_font(12 * self.scale, 500, mono=True))
        edit.setFixedWidth(self.metrics.time_w)
        edit.setFixedHeight(self.metrics.edit_h)
        edit.setPlaceholderText("--:--")

        def _norm():
            norm = normalize_time_str(edit.text(), allow_empty=allow_empty, default_str=default_str)
            if edit.text() != norm:
                edit.blockSignals(True)
                edit.setText(norm)
                edit.blockSignals(False)
            self.trigger_preview()

        edit.editingFinished.connect(_norm)
        return edit

    def make_del_btn(self, on_click) -> ui_parts.TrashButton:
        btn = ui_parts.TrashButton(dark=self.dark, scale=self.scale)
        btn.setFixedSize(self.metrics.del_w, self.metrics.del_w)
        btn.clicked.connect(on_click)
        return btn

    def make_edit_btn(self, on_click) -> ui_parts.EditButton:
        btn = ui_parts.EditButton(dark=self.dark, scale=self.scale)
        btn.setFixedSize(self.metrics.del_w, self.metrics.del_w)
        btn.clicked.connect(on_click)
        return btn

    def make_add_btn(self, text: str, on_click) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("addRowBtn")
        btn.setFixedHeight(self.metrics.add_btn_h)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoDefault(False)
        btn.setDefault(False)
        btn.clicked.connect(on_click)
        return btn

    def make_tip(self, text: str, icon_name: str = "") -> QWidget:
        t = tokens.get_tokens(self.dark)
        if not icon_name:
            lbl = QLabel(text)
            lbl.setObjectName("mutedTip")
            qss_engine.set_role(lbl, "muted", polish=False)
            lbl.setWordWrap(True)
            lbl.setFont(theme.ui_font(11.5 * self.scale, 400))
            return lbl
        w = QWidget()
        w.setObjectName("tipRow")
        h = QHBoxLayout(w)
        h.setContentsMargins(self.px(2), 0, self.px(2), 0)
        h.setSpacing(self.px(6))
        h.addWidget(icons.IconWidget(icon_name, t.text_muted, size=self.px(13)), 0, Qt.AlignmentFlag.AlignTop)
        lbl = QLabel(text)
        lbl.setObjectName("mutedTip")
        qss_engine.set_role(lbl, "muted", polish=False)
        lbl.setWordWrap(True)
        lbl.setFont(theme.ui_font(11.5 * self.scale, 400))
        h.addWidget(lbl, 1)
        return w

    def make_muted_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        qss_engine.set_role(lbl, "muted", polish=False)
        return lbl

    def style_combo_palette(self, combo: QComboBox) -> None:
        t = tokens.get_tokens(self.dark)
        view = combo.view()
        view.setAutoFillBackground(True)
        view.setMinimumWidth(self.px(170))
        pal = view.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(t.menu_bg))
        pal.setColor(QPalette.ColorRole.Text, QColor(t.text))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(t.surface_hover))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(t.text))
        view.setPalette(pal)
        container = view.window()
        if container is not None and container != combo.window():
            container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            container.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)

    def combo_min_width(self, items) -> int:
        fm = self.dialog.fontMetrics()
        longest = max((fm.horizontalAdvance(s) for s in items), default=0)
        return max(self.metrics.combo_min_w, longest + self.px(44))

    def fit_combo_to_text(self, combo: QComboBox) -> None:
        fm = combo.fontMetrics()
        need = fm.horizontalAdvance(combo.currentText()) + self.px(44)
        combo.setMinimumWidth(max(self.metrics.combo_min_w, need))

    def remove_row(self, rows: list, entry: dict, lay) -> None:
        if entry in rows:
            rows.remove(entry)
        card = entry.get("card")
        if card is not None:
            if hasattr(lay, "remove_card"):
                lay.remove_card(card)
            elif hasattr(lay, "removeWidget"):
                lay.removeWidget(card)
                card.deleteLater()
            else:
                card.setParent(None)
                card.deleteLater()
        self.schedule_preview()
