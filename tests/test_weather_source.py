"""tests/test_weather_source.py — 实时天气数据源单元测试。"""

import pytest
from app.core import sources
from app.core.sources import weather_source


def test_weather_source_registered():
    reg = sources.get_source("weather")
    assert reg is not None
    assert reg.info.id == "weather"
    assert reg.info.kind == "remote"
    assert reg.info.needs_credentials is False
    assert reg.info.default_interval_sec == 900
    assert reg.info.min_interval_sec == 60


def test_resolve_weather_desc_and_icon():
    desc, icon = weather_source.resolve_weather_desc_and_icon("Sunny", "晴")
    assert desc == "晴"
    assert icon == "☀️"

    desc, icon = weather_source.resolve_weather_desc_and_icon("Light Rain Shower", "")
    assert "雨" in desc
    assert icon in ("🌦️", "🌧️")

    desc, icon = weather_source.resolve_weather_desc_and_icon("Partly cloudy", "")
    assert desc == "多云"
    assert icon == "⛅"

    desc, _ = weather_source.resolve_weather_desc_and_icon("Extremely Extraordinary Weather Condition", "")
    assert len(desc) <= 12
    assert desc.endswith("…")


def test_temp_to_color():
    assert weather_source.temp_to_color(-5) == "#38BDF8"
    assert weather_source.temp_to_color(10) == "#0EA5E9"
    assert weather_source.temp_to_color(22) == "#10B981"
    assert weather_source.temp_to_color(30) == "#F59E0B"
    assert weather_source.temp_to_color(38) == "#EF4444"


def test_parse_wttr_json():
    mock_data = {
        "current_condition": [
            {
                "temp_C": "23",
                "FeelsLikeC": "22",
                "humidity": "58",
                "visibility": "16",
                "uvIndex": "4",
                "windspeedKmph": "12",
                "winddir16Point": "SE",
                "weatherDesc": [{"value": "Partly cloudy"}],
                "lang_zh": [{"value": "局部多云"}],
            }
        ],
        "nearest_area": [
            {
                "areaName": [{"value": "深圳"}],
                "country": [{"value": "China"}],
            }
        ],
        "weather": [
            {
                "maxtempC": "26",
                "mintempC": "18",
            }
        ],
    }

    info = weather_source.parse_wttr_json(mock_data)
    assert info["city"] == "深圳"
    assert info["temp_c"] == 23.0
    assert info["feels_like_c"] == 22.0
    assert info["humidity"] == 58
    assert info["wind_dir"] == "东南风"
    assert info["max_temp_c"] == 26.0
    assert info["min_temp_c"] == 18.0

    tiles = weather_source.weather_info_to_tiles(info)
    assert len(tiles) == 3
    t_temp, t_hum, t_wind = tiles

    assert t_temp["id"] == "weather:temp"
    assert t_temp["name"] == "深圳"
    assert t_temp["center_text"] == "23°"

    assert t_hum["id"] == "weather:humidity"
    assert t_hum["center_text"] == "58%"

    assert t_wind["id"] == "weather:wind"
    assert t_wind["center_text"] == "东南"


def test_parse_open_meteo_json():
    mock_data = {
        "current": {
            "temperature_2m": 19.5,
            "apparent_temperature": 18.0,
            "relative_humidity_2m": 62,
            "weather_code": 0,
            "wind_speed_10m": 8.5,
        },
        "daily": {
            "temperature_2m_max": [24.0],
            "temperature_2m_min": [14.0],
        },
    }

    info = weather_source.parse_open_meteo_json(mock_data, city_name="北京")
    assert info["city"] == "北京"
    assert info["temp_c"] == 19.5
    assert info["condition"] == "晴"
    assert info["icon"] == "☀️"
    assert info["max_temp_c"] == 24.0

    tiles = weather_source.weather_info_to_tiles(info)
    assert len(tiles) == 3
    assert tiles[0]["center_text"] == "20°"
