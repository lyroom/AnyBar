"""tests/test_weather_drilldown.py — 天气雷达下钻链接生成与解析测试。"""

import pytest
from app.core.sources.weather_source import (
    get_weather_radar_url,
    parse_open_meteo_json,
    parse_wttr_json,
)


def test_get_weather_radar_url_with_lat_lon():
    info = {"latitude": 39.9042, "longitude": 116.4074, "city": "北京"}
    url = get_weather_radar_url(info)
    assert "https://www.windy.com/?radar" in url
    assert "39.9042" in url
    assert "116.4074" in url


def test_get_weather_radar_url_fallback_city():
    info = {"city": "Shanghai"}
    url = get_weather_radar_url(info)
    assert "https://www.windy.com/?radar" in url
    assert "Shanghai" in url


def test_get_weather_radar_url_default():
    info = {}
    url = get_weather_radar_url(info)
    assert url == "https://www.windy.com/?radar"


def test_parse_open_meteo_includes_radar():
    dummy_data = {
        "latitude": 31.23,
        "longitude": 121.47,
        "current": {"temperature_2m": 22.5, "weather_code": 1, "is_day": 1},
        "daily": {"temperature_2m_max": [25.0], "temperature_2m_min": [18.0]},
    }
    info = parse_open_meteo_json(dummy_data, city_name="上海")
    assert info["latitude"] == 31.23
    assert info["longitude"] == 121.47
    assert "radar_url" in info
    assert "31.23" in info["radar_url"]
