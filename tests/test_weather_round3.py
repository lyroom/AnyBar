"""tests/test_weather_round3.py — 天气源缓存/并行容灾、城市变更即时重拉、回车安全、矢量图标。"""

import copy
import sys
import threading
import time

import pytest
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication, QPushButton

from app.core import config, sources
from app.core.sources import weather_source


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


INFO = {
    "city": "北京", "country": "", "temp_c": 12.5, "feels_like_c": 10.0,
    "condition": "晴", "icon": "☀️", "kind": "sun", "is_day": True, "humidity": 23,
    "wind_speed_kmh": 8.0, "wind_dir": "西南风", "visibility_km": 10.0, "uv_index": 3,
    "max_temp_c": 15.0, "min_temp_c": 3.0,
}


def test_wind_deg_to_zh():
    assert weather_source.wind_deg_to_zh(0) == "北风"
    assert weather_source.wind_deg_to_zh(225) == "西南风"
    assert weather_source.wind_deg_to_zh(None) == "微风"


def test_open_meteo_parse_has_kind_and_wind():
    info = weather_source.parse_open_meteo_json(
        {"current": {"temperature_2m": 5, "weather_code": 63, "wind_direction_10m": 90,
                     "visibility": 8000, "is_day": 0}}, "北京")
    assert info["kind"] == "rain"
    assert info["wind_dir"] == "东风"
    assert info["visibility_km"] == 8.0
    assert info["is_day"] is False


def test_cache_roundtrip_and_city_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    weather_source.save_cache("", INFO)
    cfg = {"sources": {"weather": {"city": ""}}}
    tiles, ts = weather_source.load_cached_tiles(cfg)
    assert tiles[0]["center_text"] == "12°" or tiles[0]["center_text"] == "13°"
    assert time.time() - ts < 5
    # 城市被改过 -> 旧缓存不可用，避免启动时先闪出别的城市
    assert weather_source.load_cached_tiles({"sources": {"weather": {"city": "上海"}}}) is None


def test_cache_missing_or_corrupt(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    assert weather_source.load_cached_tiles({}) is None
    (tmp_path / weather_source.CACHE_FILENAME).write_text("{not json", encoding="utf-8")
    assert weather_source.load_cached_tiles({}) is None


def test_fetch_falls_back_to_backup(monkeypatch):
    def boom(city, timeout):
        raise OSError("down")

    monkeypatch.setattr(weather_source, "fetch_open_meteo", boom)
    monkeypatch.setattr(weather_source, "fetch_wttr", lambda city, timeout: INFO)
    assert weather_source.fetch_weather_info("", 1.0) is INFO


def test_fetch_both_fail_raises(monkeypatch):
    def boom(city, timeout):
        raise OSError("down")

    monkeypatch.setattr(weather_source, "fetch_open_meteo", boom)
    monkeypatch.setattr(weather_source, "fetch_wttr", boom)
    with pytest.raises(RuntimeError):
        weather_source.fetch_weather_info("", 1.0)


def _wait(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_service_preloads_cache_and_refetches_on_city_change(qapp, monkeypatch):
    from app.core.source_service import SourceService

    calls = []
    gate = threading.Event()

    def slow_fetch(cfg, timeout=8.0):
        gate.wait(3.0)  # 模拟慢网络：期间应当已经能看到缓存状态
        calls.append(cfg["sources"]["wx"].get("city"))
        return []

    reg = sources.SourceRegistration(
        info=sources.SourceInfo(
            id="wx", title="t", kind="remote", default_interval_sec=900,
            cache_loader=lambda cfg: ([{"id": "cached"}], 123.0)),
        fetch_fn=slow_fetch,
    )
    monkeypatch.setattr(sources, "list_sources", lambda: [reg])
    monkeypatch.setattr(sources, "get_source", lambda sid: reg if sid == "wx" else None)

    cfg = {"sources": {"wx": {"enabled": True, "intervalSec": 900, "city": ""}}}
    svc = SourceService(cfg)
    try:
        # 缓存先于网络：构造完立刻有可重放的状态
        assert svc._states["wx"]["cached"] is True
        assert svc._states["wx"]["tiles"] == [{"id": "cached"}]
        gate.set()
        assert _wait(lambda: len(calls) == 1)

        # 设置未变 -> 不应重拉
        svc.configure(copy.deepcopy(cfg))
        time.sleep(0.2)
        assert len(calls) == 1

        # 城市变化 -> 立即重拉（不必等 900 秒）
        cfg2 = copy.deepcopy(cfg)
        cfg2["sources"]["wx"]["city"] = "上海"
        svc.configure(cfg2)
        assert _wait(lambda: len(calls) == 2)
        assert calls[-1] == "上海"
    finally:
        svc.shutdown()


def test_enter_in_settings_never_triggers_restore_default(qapp):
    from app.gui.settings import SettingsDialog

    dlg = SettingsDialog(None, copy.deepcopy(config.DEFAULT_CONFIG))
    btns = {b.text(): b for b in dlg.findChildren(QPushButton)}
    for name in ("恢复默认", "应用", "保存并关闭", "取消"):
        assert btns[name].autoDefault() is False
        assert btns[name].isDefault() is False
    dlg.deleteLater()


def test_glyph_paints_every_kind(qapp):
    from app.styles.weather_glyph import kind_from_emoji, paint_weather_glyph

    assert kind_from_emoji("🌧️") == "rain"
    assert kind_from_emoji("???") == "partly"
    img = QImage(64, 64, QImage.Format.Format_ARGB32)
    for kind in ("sun", "moon", "partly", "partly_night", "cloud", "rain",
                 "shower", "thunder", "snow", "fog"):
        for dark in (True, False):
            img.fill(0)
            p = QPainter(img)
            paint_weather_glyph(p, QRectF(0, 0, 64, 64), kind, dark, True)
            p.end()
            # 确实画出了像素（非全透明）
            assert any(img.pixel(x, y) >> 24 for x in range(0, 64, 4) for y in range(0, 64, 4)), kind


def test_open_meteo_forecast_parsed():
    data = {
        "current": {"time": "2026-10-27T13:15", "temperature_2m": 21, "weather_code": 2},
        "daily": {
            "time": ["2026-10-27", "2026-10-28"], "weather_code": [63, 3],
            "temperature_2m_max": [21.0, 20.6], "temperature_2m_min": [16.4, 15.4],
            "precipitation_probability_max": [87, None],
        },
        "hourly": {
            "time": [f"2026-10-27T{h:02d}:00" for h in range(24)] + [f"2026-10-28T{h:02d}:00" for h in range(24)],
            "temperature_2m": list(range(48)), "weather_code": [0] * 48, "is_day": [1] * 48,
        },
    }
    info = weather_source.parse_open_meteo_json(data, "武汉")
    assert [d["kind"] for d in info["daily"]] == ["rain", "cloud"]
    assert info["daily"][0]["pop"] == 87 and info["daily"][1]["pop"] is None
    # 从当前整点（13:00）起每 3 小时一格，共 8 格
    assert [h["time"] for h in info["hourly"]][:3] == ["13:00", "16:00", "19:00"]
    assert len(info["hourly"]) == 8
    assert info["hourly"][0]["temp"] == 13.0


def test_weekday_label():
    import datetime
    today = datetime.date(2026, 10, 27)
    assert weather_source.weekday_label("2026-10-27", today) == "今天"
    assert weather_source.weekday_label("2026-10-28", today) == "明天"
    assert weather_source.weekday_label("2026-10-29", today) == "周四"


def test_wttr_forecast_parsed():
    day = {"date": "2099-01-01", "maxtempC": "5", "mintempC": "-2",
           "hourly": [{"time": str(h * 100), "tempC": "1", "chanceofrain": "40",
                       "weatherDesc": [{"value": "Light rain"}]} for h in range(0, 24, 3)]}
    info = weather_source.parse_wttr_json({"current_condition": [{}], "weather": [day]})
    assert info["daily"][0]["max"] == 5.0 and info["daily"][0]["pop"] == 40
    assert info["daily"][0]["kind"] == "rain"
    assert info["hourly"] and info["hourly"][0]["kind"] == "rain"


def test_hover_panel_renders_forecast(qapp):
    from app.gui.hover_panel import HoverPanel
    info = dict(INFO, hourly=[{"time": "13:00", "temp": 12.0, "kind": "sun", "is_day": True}] * 8,
                daily=[{"label": "今天", "kind": "rain", "min": 3.0, "max": 15.0, "pop": 60}] * 7)
    cfg = copy.deepcopy(config.DEFAULT_CONFIG)
    panel = HoverPanel()
    panel._cfg = cfg
    panel._build_shell()
    panel._source_tiles["weather"] = weather_source.weather_info_to_tiles(info)
    panel._render()
    assert panel.findChild(object, "wxHourly") is not None
    assert panel.findChild(object, "wxDaily") is not None
    # 旧缓存/备用源缺预报字段时不应崩溃，只是少两个区块
    panel._source_tiles["weather"] = weather_source.weather_info_to_tiles(INFO)
    panel._render()
    assert panel.findChild(object, "wxDaily") is None


def test_hover_panel_hourly_now_syncs_with_live_current_after_sunset(qapp):
    """刚过日落（如 17:30）时，hourly[0] 可能仍是 17:00（is_day=True）；「现在」格须与顶部实况一致。"""
    from PySide6.QtWidgets import QLabel
    from app.gui.hover_panel import HoverPanel, WeatherGlyphWidget

    info = dict(
        INFO,
        city="武汉",
        temp_c=15.8,
        kind="sun",
        is_day=False,
        hourly=[
            {"time": "17:00", "temp": 16.7, "kind": "sun", "is_day": True},
            {"time": "20:00", "temp": 13.1, "kind": "sun", "is_day": False},
        ],
        daily=[{"label": "今天", "kind": "sun", "min": 7.5, "max": 18.8, "pop": 0}],
    )
    panel = HoverPanel()
    panel._cfg = copy.deepcopy(config.DEFAULT_CONFIG)
    panel._build_shell()
    panel._source_tiles["weather"] = weather_source.weather_info_to_tiles(info)
    panel._render()

    hourly_box = panel.findChild(object, "wxHourly")
    assert hourly_box is not None
    glyphs = hourly_box.findChildren(WeatherGlyphWidget)
    assert len(glyphs) == 2
    assert glyphs[0]._kind == "sun"
    assert glyphs[0]._is_day is False
    labels = [lbl.text() for lbl in hourly_box.findChildren(QLabel)]
    assert "现在" in labels
    assert "16°" in labels
    assert "17°" not in labels
    panel.close_now()
    panel.deleteLater()


def test_paint_weather_glyph_animation_all_kinds(qapp):
    from app.styles.weather_glyph import paint_weather_glyph
    kinds = ["sun", "moon", "partly", "partly_night", "cloud", "rain", "shower", "thunder", "snow", "fog"]
    img = QImage(64, 64, QImage.Format.Format_ARGB32_Premultiplied)
    rect = QRectF(0, 0, 64, 64)

    for kind in kinds:
        for is_day in (True, False):
            for dark in (True, False):
                # 静态
                p = QPainter(img)
                paint_weather_glyph(p, rect, kind, dark=dark, is_day=is_day, phase=0.0)
                p.end()
                # 动态相位
                p = QPainter(img)
                paint_weather_glyph(p, rect, kind, dark=dark, is_day=is_day, phase=0.35)
                p.end()
                # 闪电高光相位
                if kind == "thunder":
                    p = QPainter(img)
                    paint_weather_glyph(p, rect, kind, dark=dark, is_day=is_day, phase=0.15)
                    p.end()


def test_weather_glyph_widget_lifecycle(qapp):
    from app.gui.hover_panel import WeatherGlyphWidget
    # 静态 widget 不开定时器
    w_static = WeatherGlyphWidget("cloud", True, True, 46, animated=False)
    assert w_static._timer is None

    # 动态 widget
    w_anim = WeatherGlyphWidget("cloud", True, True, 46, animated=True)
    assert w_anim._timer is not None
    assert not w_anim._timer.isActive()

    # tick 测试
    init_phase = w_anim._phase
    w_anim._on_tick()
    # 不可见时，_on_tick 会安全停止并不步进
    assert w_anim._phase == init_phase

    # 模拟可见状态
    w_anim.setVisible(True)
    w_anim._on_tick()
    # 当有 parent 且 visible 时更新相位
    # 挂载到 dummy parent
    from PySide6.QtWidgets import QWidget
    parent = QWidget()
    w_anim.setParent(parent)
    parent.show()
    w_anim.show()
    w_anim._on_tick()
    assert w_anim._phase > init_phase

    # 隐藏时停表
    w_anim.hide()
    assert not w_anim._timer.isActive()
