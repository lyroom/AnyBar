"""app/gui/settings/pages/bar_style_page.py — 设置中心「任务栏条」页（排版配色 / 形态材质 / 跑马灯）"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QFontComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QWidget,
)

from app.gui import widgets as ui_parts
from app.platform import glass
from app.styles import qss_engine, theme, tokens

from ..form_helpers import SettingsFormContext
from .base import BaseSettingsPage

_CAPSULE_SLOT_OPTIONS = [
    ("实时天气", "weather"),
    ("CPU 占用", "cpu"),
    ("内存占用", "ram"),
    ("算力额度", "quota"),
    ("实时网速", "net"),
    ("Git 状态", "dev"),
]

_COLOR_KEYS = (
    "darkThemeColor",
    "lightThemeColor",
    "rightColor",
    "scheduleBarColor",
    "bgColor",
)


class BarStylePage(BaseSettingsPage):
    """任务栏常驻条排版配色、显示形态（长条/胶囊）与跑马灯滚动设置页。"""

    page_id = "bar_style"
    title = "任务栏条"

    def __init__(self) -> None:
        super().__init__()
        self.color_buttons: dict[str, QPushButton] = {}
        self._colors: dict[str, str] = {}
        self._font_combo: QFontComboBox | None = None
        self._size_spin: QSpinBox | None = None
        self._bold_check: ui_parts.ToggleSwitch | None = None
        self._auto_color: ui_parts.ToggleSwitch | None = None
        self.display_mode_combo: QComboBox | None = None
        self.capsule_left_combo: QComboBox | None = None
        self.capsule_right_combo: QComboBox | None = None
        self._bg_mode: QComboBox | None = None
        self._width_spin: QSpinBox | None = None
        self._speed_slider: QSlider | None = None
        self._speed_label: QLabel | None = None
        self._gap_spin: QSpinBox | None = None
        self._pause_spin: QSpinBox | None = None

    def build(self, ctx: SettingsFormContext) -> QWidget:
        self._ctx = ctx
        self.color_buttons = {}
        m = ctx.metrics
        page, lay = ctx.make_scroll_page()

        # 组 1：常驻条排版与配色
        g_typo = ui_parts.SettingGroupCard(
            ctx.dark, ctx.scale, title="常驻条排版与配色", icon_name="spark"
        )

        self._font_combo = QFontComboBox()
        self._font_combo.setFixedHeight(m.edit_h)
        self._font_combo.setMinimumWidth(
            ctx.combo_min_width(["Microsoft YaHei UI", "Segoe UI", "SimSun"])
        )
        self._font_combo.setEditable(False)
        ctx.style_combo_palette(self._font_combo)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(8, 16)
        self._size_spin.setFixedWidth(m.num_w)
        self._size_spin.setFixedHeight(m.edit_h)
        self._size_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._bold_check = ui_parts.ToggleSwitch("粗体", ctx.dark, ctx.scale)
        g_typo.add_setting_row(
            "字体与字号",
            [self._font_combo, self._size_spin, self._bold_check],
            desc="仅应用于任务栏常驻条文字（支持 8–16 档实时缩放）",
        )

        self._auto_color = ui_parts.ToggleSwitch("自动适配深浅主题", ctx.dark, ctx.scale)
        g_typo.add_setting_row(
            "文字色彩适配",
            [self._auto_color],
            desc="开启后按当前深浅主题自动匹配高对比文字色，关闭可下方自定义",
        )

        color_group = QWidget()
        color_group.setObjectName("colorGroup")
        ch = QHBoxLayout(color_group)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.setSpacing(ctx.px(8))
        self._add_color_button(ch, "darkThemeColor", "深色主字")
        self._add_color_button(ch, "lightThemeColor", "浅色主字")
        self._add_color_button(ch, "rightColor", "下行待办")
        self._add_color_button(ch, "scheduleBarColor", "日程进度")
        g_typo.add_setting_row(
            "自定义颜色",
            [color_group],
            desc="文字色仅用于常驻条；日程进度色同步用于浮窗日程条",
        )
        lay.addWidget(g_typo)

        # 组 2：形态与材质
        g_bar = ui_parts.SettingGroupCard(
            ctx.dark, ctx.scale, title="形态与材质", icon_name="capsule"
        )

        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItem("标准长条模式 (Full Bar)", "full")
        self.display_mode_combo.addItem("微型双列胶囊模式 (Compact Capsule)", "capsule")
        self.display_mode_combo.setMinimumWidth(
            ctx.combo_min_width(["标准长条模式 (Full Bar)", "微型双列胶囊模式 (Compact Capsule)"])
        )
        self.display_mode_combo.setFixedHeight(m.edit_h)
        ctx.style_combo_palette(self.display_mode_combo)
        g_bar.add_setting_row(
            "显示形态",
            [self.display_mode_combo],
            desc="长条展现全量文字与待办；双列胶囊极窄常驻（~128px），悬停平滑展开",
        )

        self.capsule_left_combo = QComboBox()
        self.capsule_left_combo.setFixedHeight(m.edit_h)
        self.capsule_left_combo.setMinimumWidth(ctx.px(114))
        self.capsule_right_combo = QComboBox()
        self.capsule_right_combo.setFixedHeight(m.edit_h)
        self.capsule_right_combo.setMinimumWidth(ctx.px(114))
        for name, val in _CAPSULE_SLOT_OPTIONS:
            self.capsule_left_combo.addItem(name, val)
            self.capsule_right_combo.addItem(name, val)
        ctx.style_combo_palette(self.capsule_left_combo)
        ctx.style_combo_palette(self.capsule_right_combo)

        g_bar.add_setting_row(
            "双列胶囊槽位",
            [
                ctx.make_muted_label("左列"),
                self.capsule_left_combo,
                ctx.make_muted_label("右列"),
                self.capsule_right_combo,
            ],
            desc="选择微型双列胶囊模式下左右两列展示的快捷指标",
        )

        self._bg_mode = QComboBox()
        self._bg_mode.addItem("液态玻璃融合 / 悬停提亮（推荐）", "glass")
        self._bg_mode.addItem("自定义纯色背景", "color")
        self._bg_mode.setMinimumWidth(
            ctx.combo_min_width(["液态玻璃融合 / 悬停提亮（推荐）", "自定义纯色背景"])
        )
        self._bg_mode.setFixedHeight(m.edit_h)
        ctx.style_combo_palette(self._bg_mode)
        self._add_color_button(None, "bgColor", "背景颜色")

        bg_group = QWidget()
        bg_group.setObjectName("bgGroup")
        bh = QHBoxLayout(bg_group)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(ctx.px(8))
        bh.addWidget(self._bg_mode)
        bh.addWidget(self.color_buttons["bgColor"])
        g_bar.add_setting_row("背景材质", [bg_group])

        self._width_spin = QSpinBox()
        self._width_spin.setRange(150, 900)
        self._width_spin.setSuffix(" px")
        self._width_spin.setFixedWidth(ctx.px(82))
        self._width_spin.setFixedHeight(m.edit_h)
        self._width_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        g_bar.add_setting_row("最大宽度上限", [self._width_spin], desc="仅标准长条模式生效")
        lay.addWidget(g_bar)

        # 组 3：跑马灯滚动
        g_motion = ui_parts.SettingGroupCard(
            ctx.dark, ctx.scale, title="跑马灯滚动", icon_name="rotate"
        )

        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setRange(10, 120)
        self._speed_slider.setFixedWidth(m.slider_w)

        self._speed_label = QLabel("30 px/s")
        self._speed_label.setFont(theme.ui_font(12 * ctx.scale, 600, mono=True))
        self._speed_label.setFixedWidth(ctx.px(68))
        self._speed_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        qss_engine.set_role(self._speed_label, "accent", polish=False)
        g_motion.add_setting_row("滚动速度", [self._speed_slider, self._speed_label])

        self._gap_spin = QSpinBox()
        self._gap_spin.setRange(20, 400)
        self._gap_spin.setFixedWidth(m.num_w)
        self._gap_spin.setFixedHeight(m.edit_h)
        self._gap_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._pause_spin = QSpinBox()
        self._pause_spin.setRange(0, 60)
        self._pause_spin.setFixedWidth(m.num_w)
        self._pause_spin.setFixedHeight(m.edit_h)
        self._pause_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)

        g_motion.add_setting_row(
            "循环间隔与停留",
            [
                ctx.make_muted_label("间隔 (px)"),
                self._gap_spin,
                ctx.make_muted_label("停留 (秒)"),
                self._pause_spin,
            ],
        )
        lay.addWidget(g_motion)
        lay.addStretch(1)
        return page

    def _add_color_button(self, layout: QHBoxLayout | None, key: str, title: str) -> None:
        assert self._ctx is not None
        ctx = self._ctx
        btn = QPushButton(title)
        btn.setFixedHeight(ctx.metrics.color_h)
        btn.setMinimumWidth(ctx.px(78))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoDefault(False)
        btn.setDefault(False)
        btn.clicked.connect(lambda: self._pick_color(key))
        self.color_buttons[key] = btn
        if layout is not None:
            layout.addWidget(btn)

    def _pick_color(self, key: str) -> None:
        assert self._ctx is not None
        ctx = self._ctx
        theme.install_qt_zh_cn_translator()
        current = QColor(self._colors.get(key, "#FFFFFF"))
        dlg = QColorDialog(current, ctx.dialog)
        dlg.setWindowTitle("选择颜色")
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dlg.setStyleSheet(theme.dialog_qss(ctx.dark, ctx.scale))
        try:
            hwnd = int(dlg.winId())
            if hwnd:
                glass.style_titlebar(hwnd, ctx.dark)
        except Exception:
            pass
        if dlg.exec() == QDialog.DialogCode.Accepted:
            color = dlg.selectedColor()
            if color.isValid():
                self._colors[key] = color.name()
                self._update_color_buttons()
                ctx.trigger_preview()
        dlg.deleteLater()

    def _update_color_buttons(self) -> None:
        if self._ctx is None:
            return
        ctx = self._ctx
        t = tokens.get_tokens(ctx.dark)
        rad = ctx.px(tokens.RADIUS["control"])
        for key, btn in self.color_buttons.items():
            c = self._colors.get(key, "#FFFFFF")
            fg = "#FFFFFF" if QColor(c).lightness() < 128 else "#11151C"
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {c}; color: {fg};"
                f" padding: 0px {ctx.px(11)}px; min-width: {ctx.px(76)}px;"
                f" border-radius: {rad}px;"
                f" border: 1px solid {t.border_strong};"
                f" font-size: {ctx.px(12)}px; font-weight: 500; }}"
                f"QPushButton:disabled {{ background-color: {t.surface_sunken};"
                f" color: {t.text_disabled}; border: 1px solid {t.border}; }}"
            )

    def _sync_auto_color_enabled(self) -> None:
        if self._auto_color is None:
            return
        custom_on = not self._auto_color.isChecked()
        for k in ("darkThemeColor", "lightThemeColor", "rightColor"):
            if k in self.color_buttons:
                self.color_buttons[k].setEnabled(custom_on)

    def _sync_bg_color_enabled(self) -> None:
        if self._bg_mode is not None and "bgColor" in self.color_buttons:
            self.color_buttons["bgColor"].setEnabled(self._bg_mode.currentIndex() == 1)

    def load(self, cfg: dict[str, Any]) -> None:
        if self._ctx is None or self._font_combo is None:
            return
        style = cfg.get("style") or {}
        for k in _COLOR_KEYS:
            if k in style:
                self._colors[k] = str(style[k])

        self._font_combo.setCurrentText(style.get("fontFamily", "Microsoft YaHei UI"))
        self._size_spin.setValue(max(8, min(16, int(style.get("fontSize", 10)))))
        self._bold_check.setChecked(bool(style.get("bold", False)))
        self._auto_color.setChecked(bool(style.get("autoColor", True)))
        self._bg_mode.setCurrentIndex(0 if style.get("bgMode", "glass") != "color" else 1)
        self._speed_slider.setValue(int(style.get("scrollSpeed", 30)))
        self._speed_label.setText(f"{self._speed_slider.value()} px/s")
        self._gap_spin.setValue(int(style.get("gapPx", 90)))
        self._pause_spin.setValue(int(style.get("scrollPauseSec", 8)))
        self._width_spin.setValue(int(style.get("width", 330)))

        disp_mode = style.get("displayMode", "full")
        self.display_mode_combo.setCurrentIndex(0 if disp_mode != "capsule" else 1)

        cl = str(style.get("capsuleLeft", "weather"))
        idx_l = self.capsule_left_combo.findData(cl)
        if idx_l >= 0:
            self.capsule_left_combo.setCurrentIndex(idx_l)

        cr = str(style.get("capsuleRight", "cpu"))
        idx_r = self.capsule_right_combo.findData(cr)
        if idx_r >= 0:
            self.capsule_right_combo.setCurrentIndex(idx_r)

        for combo in (self._font_combo, self._bg_mode):
            self._ctx.fit_combo_to_text(combo)
        self._update_color_buttons()
        self._sync_bg_color_enabled()
        self._sync_auto_color_enabled()

    def collect(self, cfg: dict[str, Any]) -> None:
        if self._font_combo is None:
            return
        style = cfg.setdefault("style", {})
        for k, v in self._colors.items():
            style[k] = v
        style["fontFamily"] = self._font_combo.currentText()
        style["fontSize"] = self._size_spin.value()
        style["bold"] = self._bold_check.isChecked()
        style["autoColor"] = self._auto_color.isChecked()
        style["bgMode"] = "color" if self._bg_mode.currentIndex() == 1 else "glass"
        style["scrollSpeed"] = self._speed_slider.value()
        style["gapPx"] = self._gap_spin.value()
        style["scrollPauseSec"] = self._pause_spin.value()
        style["width"] = self._width_spin.value()
        style["displayMode"] = "capsule" if self.display_mode_combo.currentIndex() == 1 else "full"
        style["capsuleLeft"] = str(self.capsule_left_combo.currentData() or "weather")
        style["capsuleRight"] = str(self.capsule_right_combo.currentData() or "cpu")

    def connect_preview(self) -> None:
        if self._ctx is None or self._font_combo is None:
            return
        ctx = self._ctx
        self._speed_slider.valueChanged.connect(
            lambda v: self._speed_label.setText(f"{v} px/s")
        )
        for w in (self._size_spin, self._speed_slider, self._gap_spin, self._pause_spin, self._width_spin):
            w.valueChanged.connect(ctx.schedule_preview)
        for w in (self._bold_check, self._auto_color):
            w.stateChanged.connect(ctx.schedule_preview)
        self._auto_color.stateChanged.connect(self._sync_auto_color_enabled)
        self._font_combo.currentFontChanged.connect(ctx.schedule_preview)
        self._font_combo.currentFontChanged.connect(lambda *_: ctx.fit_combo_to_text(self._font_combo))
        self._bg_mode.currentIndexChanged.connect(lambda *_: ctx.fit_combo_to_text(self._bg_mode))
        self._bg_mode.currentIndexChanged.connect(ctx.schedule_preview)
        self._bg_mode.currentIndexChanged.connect(self._sync_bg_color_enabled)
        self.display_mode_combo.currentIndexChanged.connect(ctx.schedule_preview)
        self.capsule_left_combo.currentIndexChanged.connect(ctx.schedule_preview)
        self.capsule_right_combo.currentIndexChanged.connect(ctx.schedule_preview)
