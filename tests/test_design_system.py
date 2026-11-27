"""tests/test_design_system.py — 统一设计令牌、动效引擎、矢量图标与原子组件测试。"""

import copy

import pytest
from PySide6.QtCore import QRect, Qt, qInstallMessageHandler
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QWidget

from app.core import config
from app.styles import icons, qss_engine, theme, tokens
from app.gui import widgets as ui_parts
from app.gui.widgets import motion
from app.gui.taskbar.widget import BarWidget
from app.gui.hover_panel import HoverPanel
from app.gui.settings import CodingPlanDialog, SettingsDialog


def _paint_widget(w: QWidget, width: int = 320, height: int = 120) -> QImage:
    w.resize(width, height)
    img = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    w.render(img)
    return img


class TestTokens:
    def test_concentric_radii_order(self):
        r = tokens.RADIUS
        assert r["panel"] > r["card"] > r["inner"] >= r["badge"]

    @pytest.mark.parametrize("dark", [True, False])
    def test_glass_alpha_above_hit_test_threshold(self, dark):
        t = tokens.get_tokens(dark)
        assert t.glass_top[3] >= 28
        assert t.glass_bottom[3] >= 28

    @pytest.mark.parametrize("dark", [True, False])
    def test_tier_colors_valid(self, dark):
        for ratio in (0.05, 0.35, 0.85):
            bar_c, val_c = tokens.quota_tier_colors(ratio, dark)
            assert QColor(bar_c).isValid()
            assert QColor(val_c).isValid()
            assert QColor(tokens.load_tier_color(ratio, dark)).isValid()


class TestQssParseClean:
    @pytest.mark.parametrize("dark", [True, False])
    def test_all_stylesheets_parse_without_qt_warnings(self, qapp, dark):
        warnings = []

        def _handler(_mode, _ctx, msg):
            if "parse stylesheet" in msg.lower() or "unknown property" in msg.lower():
                warnings.append(msg)

        prev = qInstallMessageHandler(_handler)
        try:
            dlg = QDialog()
            dlg.setStyleSheet(theme.settings_qss(dark, 18, 1.25))
            dlg.setStyleSheet(theme.dialog_qss(dark, 1.25))
            btn = QPushButton("x")
            btn.setStyleSheet(theme.add_row_qss(dark, 1.25))
            btn.setStyleSheet(theme.secondary_btn_qss(dark, 1.25))
            btn.setStyleSheet(theme.primary_btn_qss(dark, 1.25))
            w = QWidget()
            w.setStyleSheet(theme.menu_qss(dark, 1.25))
            w.setStyleSheet(theme.menu_qss(dark, 1.25, compact=True))
            w.setStyleSheet(theme.hover_panel_qss(dark, 1.25))
            w.setStyleSheet(theme.row_card_qss(dark, 1.25))
            w.setStyleSheet(theme.input_qss(dark, 1.25))
            dlg.deleteLater()
            btn.deleteLater()
            w.deleteLater()
            QApplication.processEvents()
        finally:
            qInstallMessageHandler(prev)
        assert warnings == [], f"QSS parse warnings detected: {warnings}"

    def test_qss_engine_templates_exist_and_cache(self):
        templates = qss_engine.list_qss_templates()
        for name in ("common", "menu", "hover_panel", "settings", "dialogs", "buttons_inputs"):
            assert name in templates
        qss_engine.clear_cache()
        s1 = qss_engine.compile_qss("hover_panel", dark=True, scale=1.25)
        s2 = qss_engine.compile_qss("hover_panel", dark=True, scale=1.25)
        assert s1 == s2 and "{{" not in s1
        with pytest.raises(KeyError):
            qss_engine.compile_template_text("QLabel { color: {{no_such_token}}; }", dark=True)


class TestVectorIcons:
    def test_all_registered_icons_render(self, qapp):
        for name in icons.ICON_PAINTERS:
            ic = icons.make_qicon(name, "#5CA4FF", size=16)
            assert not ic.isNull()
        assert not icons.app_window_icon().isNull()
        menu_icons = icons.build_menu_icons(dark=True)
        assert "capsule" in menu_icons and "spark" in menu_icons


class TestMotionAndAtomicWidgets:
    def test_blend_and_ease(self):
        c = motion.blend_color("#000000", "#FFFFFF", 0.5)
        assert 125 <= c.red() <= 130
        assert motion.ease_out_cubic(0.0) == 0.0
        assert motion.ease_out_cubic(1.0) == 1.0
        assert motion.ease_out_cubic(0.5) > 0.5

    def test_value_tween_immediate(self, qapp):
        seen = []
        tw = motion.ValueTween(0.0)
        tw.changed.connect(seen.append)
        tw.set_immediate(0.75)
        assert tw.value == 0.75
        assert seen[-1] == 0.75

    def test_collapsible_section(self, qapp):
        inner = QLabel("Drawer Content")
        sec = motion.CollapsibleSection(inner, expanded=False)
        assert sec.maximumHeight() == 0
        assert not sec.is_expanded()
        sec.set_expanded(True, animated=False)
        assert sec.is_expanded()
        assert sec.maximumHeight() > 1000
        sec.set_expanded(False, animated=False)
        assert sec.maximumHeight() == 0

    def test_toast_banner_no_disconnect_warning(self, qapp):
        import warnings
        host = QWidget()
        host.resize(500, 400)
        toast = motion.ToastBanner(host, dark=False, scale=1.0)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", RuntimeWarning)
            toast.show_message("已应用配置", kind="ok", duration_ms=100)
            toast.show_message("再次提示", kind="info", duration_ms=100)
            toast._dismiss()
            toast._on_fade_finished()
        runtime_warns = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        assert runtime_warns == [], f"Unexpected RuntimeWarning: {[str(w.message) for w in runtime_warns]}"
        assert not toast.isVisible()
        host.deleteLater()

    def test_toggle_switch_compat_and_paint(self, qapp):
        sw = ui_parts.ToggleSwitch("开启", dark=True, scale=1.25)
        toggled_vals = []
        state_vals = []
        sw.toggled.connect(toggled_vals.append)
        sw.stateChanged.connect(state_vals.append)
        sw.setChecked(True)
        assert sw.isChecked() is True
        assert toggled_vals == [True]
        assert state_vals == [Qt.CheckState.Checked.value]
        img = _paint_widget(sw, 140, 32)
        assert not img.isNull()

    def test_sliding_segmented_control(self, qapp):
        seg = ui_parts.SlidingSegmentedControl(["A", "B", "C"], dark=True, scale=1.0)
        fired = []
        seg.currentChanged.connect(fired.append)
        assert seg.count() == 3
        assert seg.currentIndex() == 0
        seg.setCurrentIndex(2, notify=True)
        assert seg.currentIndex() == 2
        assert fired == [2]
        img = _paint_widget(seg, 320, 40)
        assert not img.isNull()

    def test_pulse_status_dot_stops_timer_on_hide(self, qapp):
        dot = ui_parts.PulseStatusDot("#10B981", scale=1.0, animated=True)
        dot.show()
        QApplication.processEvents()
        assert dot._timer is not None and dot._timer.isActive()
        dot.hide()
        QApplication.processEvents()
        assert not dot._timer.isActive()
        dot.deleteLater()

    def test_animated_progress_and_gauge_render(self, qapp):
        bar = ui_parts.AnimatedProgressBar(dark=True, scale=1.0)
        bar.set_ratio(0.65)
        assert bar._ratio == 0.65
        assert not _paint_widget(bar, 200, 12).isNull()

        gauge = ui_parts.AnimatedCircularGauge(0.4, "40%", dark=True, scale=1.0)
        gauge.set_gauge_value(0.82, "82%")
        assert gauge._ratio == 0.82
        assert not _paint_widget(gauge, 60, 60).isNull()


class TestSurfacesRender:
    @pytest.mark.parametrize("dark", [True, False])
    def test_bar_widget_transition_and_ring_smoothing(self, qapp, dark, monkeypatch):
        monkeypatch.setattr(theme, "is_system_dark", lambda: dark)
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        bar = BarWidget(cfg)
        assert bar._display_ring_ratio("k1", 0.5) == 0.5
        # 更新目标值，未 tick 前仍保持平滑起点
        assert bar._display_ring_ratio("k1", 0.9) == 0.5
        bar._view_anim_progress = 0.45
        img = _paint_widget(bar, 280, 44)
        assert not img.isNull()
        bar.suspend_animations()
        bar.deleteLater()

    @pytest.mark.parametrize("dark", [True, False])
    def test_schedule_bar_fonts_fit_inside_glass_and_render_all_states(self, qapp, dark, monkeypatch):
        from PySide6.QtGui import QFontMetrics

        monkeypatch.setattr(theme, "is_system_dark", lambda: dark)
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["style"]["fontFamily"] = "华文中宋"
        cfg["style"]["fontSize"] = 14
        bar = BarWidget(cfg)
        bar._scale = 1.75
        bar_h = 77
        bar._sync_schedule_fonts(float(bar_h))

        # 光学双行块高在最大 16 档下仍严格收敛在玻璃胶囊内高之内，且 8~16 档真实递增
        inset_y = max(2.5, 3.0 * bar._scale)
        inner_h = bar_h - inset_y * 2.0
        prev_top = 0
        for fs in (8, 10, 12, 14, 16):
            cfg["style"]["fontSize"] = fs
            bar._synced_font_sig = None
            bar._sync_schedule_fonts(float(bar_h))
            fm1, fm2 = QFontMetrics(bar._font_row1), QFontMetrics(bar._font_row2)
            h1 = BarWidget._optical_line_height(bar._font_row1, fm1)
            h2 = BarWidget._optical_line_height(bar._font_row2, fm2)
            assert bar._font_row1.pixelSize() > prev_top
            assert bar._font_row2.pixelSize() < bar._font_row1.pixelSize()
            assert (h1 + h2) < inner_h
            prev_top = bar._font_row1.pixelSize()

        # 覆盖任务初期(0%/8%)、中期(45%)、专注模式、自由时间渲染均无异常
        for prog in (0.0, 0.08, 0.45):
            monkeypatch.setattr(config, "schedule_progress", lambda _c, _now, p=prog: p)
            monkeypatch.setattr(config, "current_schedule", lambda _c, _now: {"text": "晚间 · 复盘阅读"})
            bar._ring_display.clear()
            assert not _paint_widget(bar, 560, bar_h).isNull()

        bar.toggle_focus(30)
        assert not _paint_widget(bar, 560, bar_h).isNull()
        bar.toggle_focus(30)

        monkeypatch.setattr(config, "current_schedule", lambda _c, _now: None)
        bar._ring_display.clear()
        assert not _paint_widget(bar, 560, bar_h).isNull()

        bar.suspend_animations()
        bar.deleteLater()

    @pytest.mark.parametrize("dark", [True, False])
    def test_hover_panel_renders_and_toggles_drawers(self, qapp, dark, monkeypatch):
        monkeypatch.setattr(theme, "is_system_dark", lambda: dark)
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["todos"].append({"time": "10:00", "title": "已完成测试项", "note": "", "done": True})
        panel = HoverPanel()
        panel._cfg = cfg
        panel._source_tiles["system"] = [
            {"id": "system:cpu", "name": "CPU", "ratio": 0.35, "center_text": "35%", "sub_text": "8核",
             "net_up_str": "1 KB/s", "net_down_str": "2 KB/s"},
            {"id": "system:mem", "name": "RAM", "ratio": 0.55, "center_text": "55%", "mem_detail": "8G/16G"},
        ]
        panel._source_tiles["dev"] = [
            {"id": "dev:git", "branch": "master", "dirty_count": 2, "repo_path": "E:/Repo"},
        ]
        panel._build_shell()
        panel._render()
        panel._on_expand_day()
        assert panel._day_expanded is True
        panel._on_toggle_done_section()
        assert panel._done_expanded is True
        img = _paint_widget(panel, 408, 600)
        assert not img.isNull()
        panel.close_now()
        panel.deleteLater()

    @pytest.mark.parametrize("dark", [True, False])
    def test_settings_and_coding_plan_dialogs_render(self, qapp, dark, tmp_path, monkeypatch):
        monkeypatch.setattr(theme, "is_system_dark", lambda: dark)
        monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        dlg = SettingsDialog(None, cfg)
        for i in range(dlg._seg.count()):
            dlg._seg.setCurrentIndex(i, notify=True)
            img = _paint_widget(dlg, 820, 660)
            assert not img.isNull()
        # 应用后快照同步，防止取消回滚分叉
        dlg._default_edit.setText("新的自由文案")
        dlg._on_apply()
        assert dlg._snapshot["defaultText"] == "新的自由文案"
        dlg.deleteLater()

        wiz = CodingPlanDialog(None, item_data=None, dark=dark, scale=1.0)
        assert not _paint_widget(wiz, 560, 480).isNull()
        wiz.deleteLater()

    def test_theme_mode_live_switch_and_cancel_rollback(self, qapp):
        prev_mode = theme.get_theme_mode()
        try:
            cfg = copy.deepcopy(config.DEFAULT_CONFIG)
            cfg["style"]["themeMode"] = "light"
            preview_modes = []
            dlg = SettingsDialog(
                None,
                cfg,
                preview_callback=lambda c: preview_modes.append(c["style"].get("themeMode")),
            )
            assert dlg._dark is False
            assert theme.is_system_dark() is False

            # 顶部快捷按钮一键切换为深色，实时重绘并触发预览
            dlg._on_quick_toggle_theme()
            assert dlg._dark is True
            assert theme.get_theme_mode() == "dark"
            assert theme.is_system_dark() is True
            assert preview_modes[-1] == "dark"
            assert not _paint_widget(dlg, 860, 740).isNull()

            # 界面与浮窗页三段选择器切回浅色
            dlg._theme_mode_seg.setCurrentIndex(1, notify=True)
            assert dlg._dark is False
            assert theme.get_theme_mode() == "light"
            assert preview_modes[-1] == "light"

            # 切到深色后点击取消，全局主题与预览必须回滚到快照("light")
            dlg._theme_mode_seg.setCurrentIndex(2, notify=True)
            assert theme.get_theme_mode() == "dark"
            dlg._on_cancel()
            assert theme.get_theme_mode() == "light"
            assert preview_modes[-1] == "light"
            dlg.deleteLater()
        finally:
            theme.set_theme_mode(prev_mode)

    def test_qt_zh_cn_translator_localizes_color_dialog(self, qapp):
        from PySide6.QtWidgets import QColorDialog

        assert theme.install_qt_zh_cn_translator(qapp) is True
        dlg = QColorDialog()
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        labels = [w.text() for w in dlg.findChildren(QLabel) if w.text()]
        buttons = [w.text() for w in dlg.findChildren(QPushButton) if w.text()]
        dlg.deleteLater()

        assert any("基本颜色" in t for t in labels)
        assert any("自定义颜色" in t for t in labels)
        assert any("确定" in t for t in buttons)
        assert any("取消" in t for t in buttons)
