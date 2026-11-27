"""tests/test_ios_tactile_motion.py — iOS 扁平拟真天气氛围卡、轻拟物进度条入场动画与任务栏灵动反馈测试。"""

import copy

import pytest
from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from app.core import config
from app.gui import widgets as ui_parts
from app.gui.taskbar.widget import BarWidget, VIEW_QUOTA
from app.gui.hover_panel import (
    FrostedGlassTile,
    HoverPanel,
    QuotaTile,
    TempRangeBar,
    WeatherAtmosphereCard,
    weather_atmosphere_palette,
)
from app.core.sources import weather_source


def _render_img(widget, w: int = 380, h: int = 240) -> QImage:
    widget.resize(w, h)
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    widget.render(img)
    return img


class TestWeatherAtmosphere:
    @pytest.mark.parametrize(
        "kind,is_day,expected_mode",
        [
            ("sun", False, "stars"),
            ("moon", False, "stars"),
            ("sun", True, "sunbeams"),
            ("partly", True, "clouds"),
            ("partly", False, "stars_cloud"),
            ("rain", True, "rain"),
            ("thunder", False, "thunder"),
            ("snow", True, "snow"),
            ("fog", True, "fog"),
        ],
    )
    def test_atmosphere_palette_and_render(self, qapp, kind, is_day, expected_mode):
        top_c, mid_c, bot_c, mode = weather_atmosphere_palette(kind, is_day)
        assert mode == expected_mode
        assert top_c.startswith("#") and mid_c.startswith("#") and bot_c.startswith("#")

        card = WeatherAtmosphereCard(kind, is_day, scale=1.25)
        card._phase = 0.42
        img = _render_img(card, 380, 260)
        assert not img.isNull()
        card.close()
        card.deleteLater()

    def test_atmosphere_card_stops_timer_on_hide(self, qapp):
        card = WeatherAtmosphereCard("moon", False, scale=1.0)
        card.show()
        QApplication.processEvents()
        assert card._timer.isActive()
        card.hide()
        QApplication.processEvents()
        assert not card._timer.isActive()
        card.deleteLater()

    def test_atmosphere_palette_light_vs_dark_harmony(self, qapp):
        from PySide6.QtGui import QColor

        for kind, is_day in (("sun", False), ("sun", True), ("partly", False), ("rain", True), ("fog", True)):
            lt_top, lt_mid, lt_bot, lt_mode = weather_atmosphere_palette(kind, is_day, dark=False)
            dk_top, dk_mid, dk_bot, dk_mode = weather_atmosphere_palette(kind, is_day, dark=True)
            assert lt_mode == dk_mode
            # 浅色模式天气卡必须保持明亮浅调，避免在浅色悬浮窗中出现高反差深色块
            assert QColor(lt_top).lightness() >= 220
            assert QColor(lt_bot).lightness() >= 245
            # 深色模式保持与 Neutral Obsidian 同色温的克制深底
            assert QColor(dk_top).lightness() <= 60
            assert QColor(dk_bot).lightness() <= 45

            for is_dark in (False, True):
                card = WeatherAtmosphereCard(kind, is_day, scale=1.25, dark=is_dark)
                card._phase = 0.42
                img = _render_img(card, 380, 260)
                assert not img.isNull()
                card.close()
                card.deleteLater()

    def test_frosted_glass_tile_and_temp_range_bar_entrance(self, qapp):
        for is_dark in (False, True):
            tile = FrostedGlassTile(scale=1.25, interactive=True, dark=is_dark)
            img = _render_img(tile, 340, 80)
            assert not img.isNull()
            tile.deleteLater()

        bar = TempRangeBar(10.0, 18.0, 7.0, 23.0, dark=True, height=6, on_sky=True, current_temp=12.0)
        bar.show()
        bar.play_entrance(delay_ms=0)
        assert bar._reveal.is_running()
        assert not _render_img(bar, 180, 12).isNull()
        bar.hide()
        assert not bar._reveal.is_running()
        bar.deleteLater()


class TestEntranceAndTactileFeedback:
    def test_progress_bar_entrance_preserves_logical_ratio(self, qapp):
        bar = ui_parts.AnimatedProgressBar(dark=False, scale=1.25)
        bar.set_ratio(0.76)
        assert bar._ratio == 0.76
        bar.show()
        bar.play_entrance(delay_ms=0)
        assert bar._ratio == 0.76
        assert bar._tween.is_running()
        assert bar._sheen.is_running()
        assert not _render_img(bar, 260, 14).isNull()
        bar.hide()
        assert not bar._tween.is_running()
        assert not bar._sheen.is_running()
        bar.deleteLater()

    def test_quota_tile_urgent_pulse_and_hover_card(self, qapp):
        low = {"name": "小浣熊", "plan": "Free", "used": 13, "limit": 100}
        tile_low = QuotaTile(low, dark=False, index=0, scale=1.25)
        assert tile_low._dot._animated is True
        assert tile_low._dot._urgent is True
        assert tile_low._interactive is True

        high = {"name": "CodeArts", "plan": "体验版", "used": 100, "limit": 100}
        tile_high = QuotaTile(high, dark=False, index=1, scale=1.25)
        assert tile_high._dot._animated is True
        assert tile_high._dot._urgent is False
        assert not _render_img(tile_low, 360, 84).isNull()
        assert not _render_img(tile_high, 360, 84).isNull()
        tile_low.deleteLater()
        tile_high.deleteLater()

    def test_hover_panel_popup_triggers_entrance_animations(self, qapp):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["quotas"] = [
            {"name": "ZCode", "used": 76, "limit": 100},
            {"name": "小浣熊", "used": 13, "limit": 100},
        ]
        info = {
            "city": "武汉", "country": "", "temp_c": 12.0, "feels_like_c": 11.0,
            "condition": "晴", "icon": "☀️", "kind": "sun", "is_day": False,
            "humidity": 76, "wind_speed_kmh": 2.0, "wind_dir": "东风",
            "max_temp_c": 18.0, "min_temp_c": 10.0,
            "hourly": [{"time": "23:00", "temp": 12.0, "kind": "moon", "is_day": False}] * 8,
            "daily": [{"label": "今天", "kind": "cloud", "min": 10.0, "max": 18.0, "pop": None}] * 3,
        }
        panel = HoverPanel()
        panel._cfg = cfg
        panel._source_tiles["weather"] = weather_source.weather_info_to_tiles(info)
        panel._build_shell()
        panel._render()
        assert isinstance(panel._weather_card, WeatherAtmosphereCard)
        assert len(panel._temp_range_bars) == 3

        panel.popup_animated(QPoint(100, 100), QSize(408, 620))
        assert panel._quota_tiles[0].bar._delay_timer.isActive()
        assert panel._temp_range_bars[0]._delay_timer.isActive()
        img = _render_img(panel, 408, 620)
        assert not img.isNull()
        panel.close_now()

        # 关闭后面板内绝不允许残余活跃定时器（0fps 休眠）
        from PySide6.QtCore import QTimer
        active_timers = [tm for tm in panel.findChildren(QTimer) if tm.isActive()]
        assert active_timers == []
        panel.deleteLater()

    def test_hover_panel_reuses_cards_when_unchanged(self, qapp, monkeypatch):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["panelCards"] = [{"id": "quotas", "enabled": True}]
        cfg["quotas"] = [{"name": "ZCode", "used": 76, "limit": 100}]
        panel = HoverPanel()
        anchor = QRect(1200, 1000, 320, 44)
        render_count = [0]
        orig_render = panel._render

        def _counted():
            render_count[0] += 1
            orig_render()

        monkeypatch.setattr(panel, "_render", _counted)

        panel.popup(cfg, anchor)
        panel.close_now()
        assert render_count[0] == 1

        # 配置与数据未变时再次悬停弹出，直接复用卡片树
        panel.popup(cfg, anchor)
        panel.close_now()
        assert render_count[0] == 1

        # 配置改动后自动重新渲染
        cfg["quotas"][0]["used"] = 50
        panel.popup(cfg, anchor)
        panel.close_now()
        assert render_count[0] == 2
        panel.deleteLater()

    def test_bar_widget_hover_sheen_and_idle_zero_repaint(self, qapp):
        import time
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["quotas"] = [
            {"name": "ZCode", "used": 76, "limit": 100},
            {"name": "小浣熊", "used": 13, "limit": 100},
            {"name": "CodeArts", "used": 100, "limit": 100},
        ]
        cfg["style"]["barView"] = VIEW_QUOTA
        bar = BarWidget(cfg)
        bar.set_hover(True)
        assert bar._hover_sheen < 0.0
        img = _render_img(bar, 360, 44)
        assert not img.isNull()

        # 空闲态（未悬停、流光与脉冲已过）：即使存在 13% 告急项也应 0fps 零重绘
        bar.set_hover(False)
        bar._hover_progress = 0.0
        bar._view_anim_progress = 1.0
        bar._hover_sheen = 2.0
        bar._urgent_pulse_until = 0.0
        bar._ring_targets.clear()
        repaints = [0]
        bar.repaint = lambda: repaints.__setitem__(0, repaints[0] + 1)
        bar._swp_frame = lambda now: None
        for _ in range(10):
            bar._last_ts = time.monotonic() - 0.025
            bar._tick()
        assert repaints[0] == 0

        bar.suspend_animations()
        bar.deleteLater()


class TestFocusAndNoFlickerFixes:
    def test_todo_input_focus_out_and_deactivate_allows_hide(self, qapp, monkeypatch):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QFocusEvent

        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["panelCards"] = [{"id": "todos", "enabled": True}]
        panel = HoverPanel()
        anchor = QRect(1200, 1000, 320, 44)
        panel.popup(cfg, anchor)
        panel._stop_anims()
        panel.setWindowOpacity(1.0)

        # 模拟点击输入框并输入草稿文本
        panel._input_focused = True
        panel._add_input.setText("未提交的待办草稿")

        # 鼠标已移出浮窗和任务栏常驻条
        monkeypatch.setattr(panel, "_cursor_inside_panel_or_anchor", lambda: False)

        # 1. FocusOut 应立刻释放 _input_focused 并启动隐藏倒计时
        panel.eventFilter(panel._add_input, QFocusEvent(QEvent.Type.FocusOut))
        assert panel._input_focused is False
        assert panel._hide_timer.isActive()

        # 2. 即便之前残留 _input_focused=True 且输入框有草稿，窗口失活（点击外部软件）也必须立即收起浮窗且保留草稿
        panel._hide_timer.stop()
        panel._input_focused = True
        panel.changeEvent(QEvent(QEvent.Type.WindowDeactivate))
        assert panel._input_focused is False
        assert panel._hiding is True
        assert panel._add_input.text() == "未提交的待办草稿"

        panel.close_now()
        panel.deleteLater()

    def test_todo_input_idle_timeout_hides_even_with_draft_text(self, qapp, monkeypatch):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["panelCards"] = [{"id": "todos", "enabled": True}]
        panel = HoverPanel()
        panel.popup(cfg, QRect(1200, 1000, 320, 44))
        panel._stop_anims()
        panel._input_focused = True
        panel._add_input.setText("草稿")
        monkeypatch.setattr(panel, "_cursor_inside_panel_or_anchor", lambda: False)

        panel._on_input_idle()
        assert panel._input_focused is False
        assert panel._hide_timer.isActive()
        assert panel._add_input.text() == "草稿"

        panel.close_now()
        panel.deleteLater()

    def test_system_and_dev_periodic_updates_do_not_relayout_or_rerender(self, qapp, monkeypatch):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["panelCards"] = [
            {"id": "system", "enabled": True},
            {"id": "dev", "enabled": True},
        ]
        cfg["sources"]["system"]["enabled"] = True
        cfg["sources"]["dev"]["enabled"] = True

        panel = HoverPanel()
        panel._cfg = cfg
        sys_tiles = [
            {"id": "system:cpu", "name": "CPU", "ratio": 0.25, "center_text": "25%", "sub_text": "16核",
             "net_up_str": "1 KB/s", "net_down_str": "2 KB/s"},
            {"id": "system:mem", "name": "RAM", "ratio": 0.55, "center_text": "55%", "mem_detail": "17G/32G"},
        ]
        dev_tiles = [{"id": "dev:git", "branch": "main", "dirty_count": 1, "repo_path": "E:/Repo"}]
        panel._source_tiles["system"] = copy.deepcopy(sys_tiles)
        panel._source_tiles["dev"] = copy.deepcopy(dev_tiles)
        panel._build_shell()
        panel._render()
        panel.setVisible(True)

        render_calls = [0]
        fixup_calls = [0]
        monkeypatch.setattr(panel, "_render", lambda: render_calls.__setitem__(0, render_calls[0] + 1))
        monkeypatch.setattr(panel, "_fixup_height", lambda: fixup_calls.__setitem__(0, fixup_calls[0] + 1))

        # 模拟 system 每 2 秒定时刷新：既不能重建，也不能触发 _fixup_height 闪烁
        sys_tiles[0]["center_text"] = "31%"
        sys_tiles[0]["ratio"] = 0.31
        panel.set_source_tiles("system", copy.deepcopy(sys_tiles))
        assert render_calls[0] == 0
        assert fixup_calls[0] == 0
        assert panel._system_boxes["CPU"][0].text() == "31%"

        # 模拟 dev 每 5 秒定时刷新：原位更新，不能重建也不能触发 _fixup_height
        dev_tiles[0]["dirty_count"] = 3
        panel.set_source_tiles("dev", copy.deepcopy(dev_tiles))
        assert render_calls[0] == 0
        assert fixup_calls[0] == 0
        assert "3" in panel._dev_widgets["status"].text()

        panel.close_now()
        panel.deleteLater()

    def test_add_todo_and_expand_day_no_rerender_or_width_thrashing(self, qapp, monkeypatch):
        """回归验证：添加待办回车走原位局部刷新（不整窗重建、不重设 DWM 圆角），
        且触顶态展开日程不产生 avail_w <-> avail_w-8 宽度震荡。"""
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        for c in cfg["panelCards"]:
            c["enabled"] = True

        panel = HoverPanel()
        panel._source_tiles["system"] = [
            {"id": "system:cpu", "name": "CPU", "ratio": 0.15, "center_text": "15%", "sub_text": "16核",
             "net_up_str": "10 KB/s", "net_down_str": "20 KB/s"},
            {"id": "system:mem", "name": "RAM", "ratio": 0.55, "center_text": "55%", "mem_detail": "17G/32G"},
            {"id": "system:disk", "name": "Disk", "ratio": 0.72, "center_text": "72%", "disk_detail": "180G/250G"},
        ]
        info = {
            "city": "武汉", "country": "", "temp_c": 15.0, "feels_like_c": 13.0,
            "condition": "霾", "icon": "🌫️", "kind": "fog", "is_day": True,
            "humidity": 65, "wind_speed_kmh": 5.0, "wind_dir": "北风",
            "max_temp_c": 18.0, "min_temp_c": 10.0,
            "hourly": [{"time": f"{h:02d}:00", "temp": 14.0, "kind": "fog", "is_day": True} for h in range(8)],
            "daily": [{"label": f"周{i}", "kind": "sun", "min": 10.0, "max": 18.0, "pop": 10} for i in range(7)],
        }
        panel._source_tiles["weather"] = weather_source.weather_info_to_tiles(info)

        anchor = QRect(1600, 1000, 400, 44)
        panel.popup(cfg, anchor)
        panel._stop_anims()
        panel.setWindowOpacity(1.0)
        QApplication.processEvents()

        old_header = panel._header
        old_weather = panel._weather_card
        old_system = panel._system_card

        render_calls = [0]
        glass_calls = [0]
        maxw_calls = []
        orig_render = panel._render
        orig_glass = panel._apply_glass
        orig_mw = panel._body.setMaximumWidth

        monkeypatch.setattr(panel, "_render", lambda: (render_calls.__setitem__(0, render_calls[0] + 1), orig_render()))
        monkeypatch.setattr(panel, "_apply_glass", lambda: (glass_calls.__setitem__(0, glass_calls[0] + 1), orig_glass()))
        monkeypatch.setattr(panel._body, "setMaximumWidth", lambda v: (maxw_calls.append(v), orig_mw(v)))

        # 1. 原位添加待办：不能触发整窗 _render，其他卡片实例必须原封不动复用，不重复调 DWM
        cfg["todos"].append({"time": "19:20", "title": "无闪烁新待办", "note": "", "done": False})
        ok = panel.sync_todos_inplace(cfg, anchor, keep_focus=True)
        QApplication.processEvents()
        assert ok is True
        assert render_calls[0] == 0
        assert glass_calls[0] == 0
        assert maxw_calls == []
        assert panel._header is old_header
        assert panel._weather_card is old_weather
        assert panel._system_card is old_system
        assert any(r._plain == "无闪烁新待办" for r in panel._todo_rows.values())

        # 2. 展开全部日程：_body.maximumWidth 不得出现 8px 横跳震荡
        panel._on_expand_day()
        for _ in range(8):
            QApplication.processEvents()
        assert maxw_calls == []
        assert render_calls[0] == 0

        panel.close_now()
        panel.deleteLater()
