import copy
import sys
from PySide6.QtWidgets import QApplication
import pytest

from app.core import config
from app.gui.hover_panel import HoverPanel
from app.gui.settings import SettingsDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class TestHoverPanelCardsOrder:
    def test_default_rendering(self, qapp):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        panel = HoverPanel()
        panel._cfg = cfg
        panel._build_shell()
        panel._render()
        # 默认有日程、待办卡片等被渲染，且末尾有 stretch
        assert panel._content.count() >= 2
        assert panel._header is not None

    def test_disabled_schedule_card(self, qapp):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        for c in cfg["panelCards"]:
            if c["id"] == "schedule":
                c["enabled"] = False
        panel = HoverPanel()
        panel._cfg = cfg
        panel._build_shell()
        panel._render()
        # 日程卡片被禁用，_header 为 None
        assert panel._header is None
        # _refresh_now 不会崩溃
        panel._refresh_now()

    def test_custom_card_order(self, qapp):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        # 调整顺序：todos 放在第一位，schedule 放在第二位
        cfg["panelCards"] = [
            {"id": "todos", "enabled": True},
            {"id": "schedule", "enabled": True},
        ]
        panel = HoverPanel()
        panel._cfg = cfg
        panel._build_shell()
        panel._render()
        # 两个卡片 + 1 个 stretch = 3
        assert panel._content.count() == 3

    def test_all_cards_disabled_shows_placeholder(self, qapp):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["panelCards"] = [{"id": c["id"], "enabled": False} for c in cfg["panelCards"]]
        panel = HoverPanel()
        panel._cfg = cfg
        panel._build_shell()
        panel._render()
        # 显示空态卡片 + stretch = 2
        assert panel._content.count() == 2


class TestSettingsDialogPanelCards:
    def test_dialog_cards_page(self, qapp):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        dlg = SettingsDialog(None, cfg)
        # 6 个标签页（按载体拆清：任务栏条 / 界面与浮窗）
        assert dlg._seg.count() == 6
        assert dlg._seg._items[2] == "任务栏条"
        assert dlg._seg._items[3] == "界面与浮窗"
        assert len(dlg._panel_card_items) == 6

        # 测试上移与下移
        first_id = dlg._panel_card_items[0]["id"]
        second_id = dlg._panel_card_items[1]["id"]

        # 上移第二项
        dlg._panel_card_items[0], dlg._panel_card_items[1] = (
            dlg._panel_card_items[1],
            dlg._panel_card_items[0],
        )
        dlg._refresh_panel_cards_ui()
        dlg._collect_config()

        assert dlg._cfg["panelCards"][0]["id"] == second_id
        assert dlg._cfg["panelCards"][1]["id"] == first_id

        # 测试恢复默认
        dlg._reset_panel_cards_to_default()
        dlg._collect_config()
        assert dlg._cfg["panelCards"][0]["id"] == "schedule"
        assert dlg._cfg["panelCards"][1]["id"] == "todos"



    def test_personalization_capsule_and_git_repo(self, qapp):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["style"]["capsuleLeft"] = "ram"
        cfg["style"]["capsuleRight"] = "quota"
        cfg["sources"]["dev"]["repoPath"] = "D:/TestRepo"
        dlg = SettingsDialog(None, cfg)
        assert dlg._capsule_left_combo.currentData() == "ram"
        assert dlg._capsule_right_combo.currentData() == "quota"
        assert dlg._source_widgets["dev"]["repoPath"].text() == "D:/TestRepo"

        dlg._display_mode_combo.setCurrentIndex(1)  # capsule
        dlg._capsule_left_combo.setCurrentIndex(0)  # weather
        dlg._capsule_right_combo.setCurrentIndex(1)  # cpu
        dlg._source_widgets["dev"]["repoPath"].setText("E:/AnotherRepo")
        dlg._collect_config()

        assert dlg._cfg["style"]["displayMode"] == "capsule"
        assert dlg._cfg["style"]["capsuleLeft"] == "weather"
        assert dlg._cfg["style"]["capsuleRight"] == "cpu"
        assert dlg._cfg["sources"]["dev"]["repoPath"] == "E:/AnotherRepo"


class TestQuotaInplaceUpdate:
    def test_quota_tile_update_data(self, qapp):
        from app.gui.hover_panel import QuotaTile
        data = {
            "name": "ZCode",
            "plan": "团队套餐标准版",
            "used": 100,
            "limit": 100,
            "windows": [{"name": "5h 窗口", "remaining_percent": 100.0, "remaining": 100, "total": 100}],
        }
        tile = QuotaTile(data, dark=False, index=0, scale=1.0)
        assert tile.name_lbl.text() == "ZCode"
        assert "100%" in tile.value_lbl.text()
        assert tile.bar._ratio == 1.0

        # 原地更新数据为 65%
        new_data = {
            "name": "ZCode",
            "plan": "团队套餐标准版",
            "used": 65,
            "limit": 100,
            "windows": [{"name": "5h 窗口", "remaining_percent": 65.0, "remaining": 65, "total": 100}],
        }
        tile.update_data(new_data)
        assert "65%" in tile.value_lbl.text()
        assert tile.bar._ratio == 0.65

    def test_panel_inplace_update_quota(self, qapp, monkeypatch):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["quotas"] = [
            {"name": "ZCode", "plan": "标准版", "used": 50, "limit": 100},
            {"name": "Codex", "plan": "Plus", "used": 80, "limit": 100},
        ]
        panel = HoverPanel()
        panel._cfg = cfg
        panel._build_shell()
        panel._render()
        panel.setVisible(True)

        assert len(panel._quota_tiles) == 2
        assert "50%" in panel._quota_tiles[0].value_lbl.text()

        # 模拟数据源派发更新
        render_called = [False]
        orig_render = panel._render

        def _mock_render():
            render_called[0] = True
            orig_render()

        monkeypatch.setattr(panel, "_render", _mock_render)

        # 结构相同、数值改变：应走原地刷新，不应调用 _render
        panel._cfg["quotas"][0]["used"] = 90
        panel.set_quota_state({"state": "ok", "ts": 1700000000})

        assert render_called[0] is False
        assert "90%" in panel._quota_tiles[0].value_lbl.text()

        # 套餐结构发生增减：应退回 _render
        panel._cfg["quotas"].append({"name": "NewPlan", "used": 10, "limit": 100})
        panel.set_quota_state({"state": "ok", "ts": 1700000001})
        assert render_called[0] is True

    def test_disabled_system_card_does_not_rerender(self, qapp, monkeypatch):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        for c in cfg["panelCards"]:
            if c["id"] == "system":
                c["enabled"] = False
        panel = HoverPanel()
        panel._cfg = cfg
        panel._build_shell()
        panel._render()
        panel.setVisible(True)
        called = []
        monkeypatch.setattr(panel, "_render", lambda: called.append(1))
        panel.set_source_tiles("system", [
            {"name": "CPU", "center_text": "1%", "sub_text": ""}])
        assert called == []

    def test_panel_inplace_update_system_source(self, qapp, monkeypatch):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["sources"] = {"system": {"enabled": True}}
        cfg["panelCards"] = [{"id": "system", "enabled": True}]
        panel = HoverPanel()
        panel._cfg = cfg
        panel._source_tiles["system"] = [
            {"name": "CPU", "center_text": "12%", "sub_text": "Normal"},
            {"name": "RAM", "center_text": "55%", "sub_text": "8.8G/16G"},
        ]
        panel._build_shell()
        panel._render()
        panel.setVisible(True)

        assert "CPU" in panel._system_boxes
        assert panel._system_boxes["CPU"][0].text() == "12%"

        render_called = [False]
        monkeypatch.setattr(panel, "_render", lambda: render_called.__setitem__(0, True))

        # 数值更新，走原地更新
        panel.set_source_tiles("system", [
            {"name": "CPU", "center_text": "28%", "sub_text": "Normal"},
            {"name": "RAM", "center_text": "58%", "sub_text": "9.2G/16G"},
        ])
        assert render_called[0] is False
        assert panel._system_boxes["CPU"][0].text() == "28%"


class TestUserMenuRefresh:
    def test_user_refresh_emits_and_triggers_source_refresh(self, qapp, monkeypatch):
        from app.gui.taskbar.widget import BarWidget
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        bar = BarWidget(cfg)

        signal_emitted = []
        bar.request_refresh.connect(lambda: signal_emitted.append(True))

        content_refreshed = []
        monkeypatch.setattr(bar, "refresh_content", lambda: content_refreshed.append(True))

        bar._on_user_refresh()
        assert content_refreshed == [True]
        assert signal_emitted == [True]


class TestWeatherCardIntegration:
    def test_weather_card_rendered_and_inplace_updated(self, qapp, monkeypatch):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["sources"]["weather"] = {"enabled": True, "intervalSec": 900}
        panel = HoverPanel()
        panel._cfg = cfg
        panel._build_shell()

        weather_tiles = [
            {
                "id": "weather:temp",
                "source": "weather",
                "name": "深圳",
                "center_text": "22°",
                "sub_text": "晴",
                "weather_info": {
                    "city": "深圳",
                    "temp_c": 22.0,
                    "condition": "晴",
                    "icon": "☀️",
                    "feels_like_c": 21.0,
                    "max_temp_c": 26.0,
                    "min_temp_c": 18.0,
                },
            },
            {
                "id": "weather:humidity",
                "source": "weather",
                "name": "湿度",
                "center_text": "55%",
                "sub_text": "体感 21°",
            },
            {
                "id": "weather:wind",
                "source": "weather",
                "name": "风向",
                "center_text": "东风",
                "sub_text": "12 km/h",
            },
        ]

        panel._source_tiles["weather"] = weather_tiles
        panel._render()

        assert getattr(panel, "_weather_card", None) is not None
        assert "temp" in panel._weather_boxes
        assert panel._weather_boxes["temp"].text() == "22°"
        assert "📍 深圳" in panel._weather_boxes["city"].text()

        # 天气卡含逐小时/逐日预报，结构复杂：面板可见时数据更新走整卡重绘（15 分钟一次）
        panel.show()
        render_called = [False]
        monkeypatch.setattr(panel, "_render", lambda: render_called.__setitem__(0, True))
        panel.set_source_tiles("weather", copy.deepcopy(weather_tiles))
        assert render_called[0] is True
        panel.hide()

    def test_bar_widget_weather_view(self, qapp):
        from app.gui.taskbar.widget import BarWidget, VIEW_WEATHER
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["sources"]["weather"] = {"enabled": True}
        bar = BarWidget(cfg)

        weather_tiles = [
            {"id": "weather:temp", "name": "北京", "center_text": "18°", "sub_text": "晴"},
            {"id": "weather:humidity", "name": "湿度", "center_text": "40%", "sub_text": "体感 17°"},
        ]
        bar.set_source_tiles("weather", weather_tiles)

        views = bar.available_views()
        assert VIEW_WEATHER in views

        bar.toggle_view(VIEW_WEATHER)
        assert bar.current_view() == VIEW_WEATHER
        assert bar.is_tiles_view() is False
        assert bar.is_weather_view() is True
        row1, row2 = bar.current_texts()
        assert "北京" in row1 and "晴" in row1






    def test_system_probe_card_and_inplace_update(self, qapp, monkeypatch):
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["sources"]["system"] = {"enabled": True}
        panel = HoverPanel()
        panel._cfg = cfg
        panel._build_shell()

        sys_tiles = [
            {
                "id": "system:cpu",
                "source": "system",
                "name": "CPU",
                "ratio": 0.20,
                "center_text": "20%",
                "sub_text": "24核",
                "host_name": "TestNode-ARM",
                "os_name": "Windows 11",
                "net_up_str": "765 B/s",
                "net_down_str": "214 B/s",
                "net_traffic_str": "累计 20.8 GB",
                "uptime_str": "在线 60天",
                "latencies": {"ct": 35, "cu": 40, "cm": 45},
            },
            {
                "id": "system:mem",
                "source": "system",
                "name": "RAM",
                "ratio": 0.39,
                "center_text": "39%",
                "sub_text": "25.4G / 64G",
            },
            {
                "id": "system:disk",
                "source": "system",
                "name": "Disk",
                "ratio": 0.87,
                "center_text": "87%",
                "sub_text": "220G / 256G",
            },
        ]
        panel._source_tiles["system"] = sys_tiles
        panel._render()

        assert getattr(panel, "_system_card", None) is not None
        assert "CPU" in panel._system_boxes
        assert panel._system_boxes["CPU"][0].text() == "20%"
        assert panel._system_boxes["RAM"][0].text() == "39%"
        assert panel._system_boxes["Disk"][0].text() == "87%"
        assert "speed" in panel._system_detail_labels
        assert "↑ 765 B/s" in panel._system_detail_labels["speed"].text()

        # 原位更新验证
        panel.setVisible(True)
        render_called = [False]
        monkeypatch.setattr(panel, "_render", lambda: render_called.__setitem__(0, True))

        updated_tiles = copy.deepcopy(sys_tiles)
        updated_tiles[0]["center_text"] = "35%"
        updated_tiles[0]["net_up_str"] = "1.2 MB/s"

        panel.set_source_tiles("system", updated_tiles)
        assert render_called[0] is False
        assert panel._system_boxes["CPU"][0].text() == "35%"
        assert "↑ 1.2 MB/s" in panel._system_detail_labels["speed"].text()
        panel.hide()

    def test_bar_widget_system_probe_view(self, qapp):
        from app.gui.taskbar.widget import BarWidget, VIEW_SYSTEM
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["sources"]["system"] = {"enabled": True}
        bar = BarWidget(cfg)

        sys_tiles = [
            {
                "id": "system:cpu",
                "source": "system",
                "name": "CPU",
                "ratio": 0.20,
                "center_text": "20%",
                "sub_text": "24核",
                "net_up_str": "765 B/s",
                "net_down_str": "214 B/s",
            },
            {
                "id": "system:mem",
                "source": "system",
                "name": "RAM",
                "ratio": 0.39,
                "center_text": "39%",
                "sub_text": "25.4G",
            },
            {
                "id": "system:disk",
                "source": "system",
                "name": "Disk",
                "ratio": 0.87,
                "center_text": "87%",
                "sub_text": "余33G",
            },
        ]
        bar.set_source_tiles("system", sys_tiles)
        bar.toggle_view(VIEW_SYSTEM)
        assert bar.current_view() == VIEW_SYSTEM
        assert bar.is_system_view() is True

        cur_tiles = bar.current_tiles()
        names = [t["name"] for t in cur_tiles]
        assert names == ["CPU", "RAM", "Disk"]

        # 测算布局：3 项标准满高圆环
        cells, total = bar._tiles_layout(300, 36.0)
        assert len(cells) == 3
        assert total > 100.0


class TestMenuPausePlayIcon:
    def test_menu_icons_has_play_and_pause(self, qapp):
        from app.gui import widgets as ui_parts
        icons = ui_parts.build_menu_icons(dark=True)
        assert "pause" in icons
        assert "play" in icons
        assert "capsule" in icons
        assert "rotate" in icons
        assert "check" in icons
        assert not icons["pause"].isNull()
        assert not icons["play"].isNull()
        assert not icons["capsule"].isNull()
        assert not icons["rotate"].isNull()
        assert not icons["check"].isNull()

    def test_toggle_pause_action_icon_switch(self, qapp, monkeypatch):
        from app.gui.taskbar.widget import BarWidget
        from PySide6.QtWidgets import QMenu
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        bar = BarWidget(cfg)
        assert bar.is_paused() is False

        captured_actions = []
        orig_init = QMenu.__init__

        def fake_init(menu_self, *args, **kwargs):
            orig_init(menu_self, *args, **kwargs)
            menu_self.addAction = lambda act: captured_actions.append(act)
            menu_self.exec = lambda *a, **k: None

        monkeypatch.setattr(QMenu, "__init__", fake_init)

        bar._show_menu(None)
        pause_act = [a for a in captured_actions if hasattr(a, 'text') and ("暂停滚动" in a.text() or "恢复滚动" in a.text() or "暂停" in a.text() or "恢复" in a.text())][0]
        assert "暂停" in pause_act.text()

        # 切换为暂停后
        bar.toggle_pause()
        assert bar.is_paused() is True

        captured_actions.clear()
        bar._show_menu(None)
        resume_act = [a for a in captured_actions if hasattr(a, 'text') and ("暂停滚动" in a.text() or "恢复滚动" in a.text() or "暂停" in a.text() or "恢复" in a.text())][0]
        assert "恢复" in resume_act.text()


def test_dev_card_disabled_not_rendered(qapp):
    from app.gui.hover_panel import HoverPanel
    from app.core.tiles import make_tile
    cfg = copy.deepcopy(config.DEFAULT_CONFIG)
    for c in cfg["panelCards"]:
        if c["id"] == "dev":
            c["enabled"] = False
    panel = HoverPanel()
    panel._cfg = cfg
    panel._build_shell()
    panel._source_tiles["dev"] = [make_tile(id="git:branch", source="dev", name="Git", center_text="master", sub_text="clean")]
    panel._render()
    from PySide6.QtWidgets import QLabel
    labels = panel.findChildren(QLabel)
    git_texts = [lbl.text() for lbl in labels if "Git" in lbl.text() or "master" in lbl.text()]
    assert not git_texts, f"Expected no Git card labels, but found: {git_texts}"

def test_hide_when_already_hidden_does_not_create_anim(qapp):
    panel = HoverPanel()
    assert not panel.isVisible()
    panel.hide()
    assert panel._hide_anim is None
    assert not panel._hiding

