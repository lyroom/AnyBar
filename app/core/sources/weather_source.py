"""app/sources/weather_source.py — 实时天气数据源（气温、天气状况、湿度、风向与体感）

开箱即用、无需 API Key：
- Open-Meteo（主）：全球公开气象服务，国内直连快；城市名走其地理编码，留空则按 IP 定位。
- wttr.in（备）：与主源并行发起，主源失败时直接采用其结果，避免串行等待超时。
- 磁盘缓存：每次成功拉取后落盘，下次启动立即用缓存出图，网络结果回来后再平滑刷新。
"""

from __future__ import annotations

import concurrent.futures
import datetime
import json
import time
import urllib.parse
import urllib.request
from typing import Any

from app.core.tiles import make_tile

from . import SourceInfo, register

CACHE_FILENAME = "weather_cache.json"
CACHE_MAX_AGE_SEC = 24 * 3600

# WMO Weather interpretation codes -> (中文描述, Emoji, 矢量图标种类)
WMO_CODE_MAP: dict[int, tuple[str, str, str]] = {
    0: ("晴", "☀️", "sun"),
    1: ("晴间多云", "🌤️", "partly"),
    2: ("多云", "⛅", "partly"),
    3: ("阴", "☁️", "cloud"),
    45: ("雾", "🌫️", "fog"),
    48: ("浓雾", "🌫️", "fog"),
    51: ("毛毛雨", "🌦️", "shower"),
    53: ("小雨", "🌧️", "rain"),
    55: ("中雨", "🌧️", "rain"),
    56: ("冻雨", "🌨️", "rain"),
    57: ("强冻雨", "🌨️", "rain"),
    61: ("小雨", "🌧️", "rain"),
    63: ("中雨", "🌧️", "rain"),
    65: ("大雨", "🌧️", "rain"),
    66: ("冻雨", "🌨️", "rain"),
    67: ("暴雨", "🌧️", "rain"),
    71: ("小雪", "🌨️", "snow"),
    73: ("中雪", "❄️", "snow"),
    75: ("大雪", "❄️", "snow"),
    77: ("雪粒", "❄️", "snow"),
    80: ("小阵雨", "🌦️", "shower"),
    81: ("阵雨", "🌦️", "shower"),
    82: ("强阵雨", "🌧️", "rain"),
    85: ("小阵雪", "🌨️", "snow"),
    86: ("阵雪", "❄️", "snow"),
    95: ("雷阵雨", "⛈️", "thunder"),
    96: ("雷雨冰雹", "⛈️", "thunder"),
    99: ("强雷雨冰雹", "⛈️", "thunder"),
}

# 英文天气常见关键词 -> (中文, Emoji, 图标种类)，长词组在前优先匹配
KEYWORD_MAP: list[tuple[str, str, str, str]] = [
    ("thunder", "雷阵雨", "⛈️", "thunder"),
    ("heavy rain", "大雨", "🌧️", "rain"),
    ("moderate rain at times", "时有中雨", "🌧️", "rain"),
    ("patchy rain", "局部阵雨", "🌦️", "shower"),
    ("light rain shower", "局部小雨", "🌦️", "shower"),
    ("light rain", "小雨", "🌧️", "rain"),
    ("moderate rain", "中雨", "🌧️", "rain"),
    ("shower", "阵雨", "🌦️", "shower"),
    ("drizzle", "毛毛雨", "🌦️", "shower"),
    ("rain", "雨", "🌧️", "rain"),
    ("heavy snow", "大雪", "❄️", "snow"),
    ("light snow", "小雪", "🌨️", "snow"),
    ("snow", "雪", "❄️", "snow"),
    ("sleet", "雨夹雪", "🌨️", "snow"),
    ("fog", "雾", "🌫️", "fog"),
    ("mist", "薄雾", "🌫️", "fog"),
    ("haze", "霾", "🌫️", "fog"),
    ("overcast", "阴天", "☁️", "cloud"),
    ("partly cloudy", "多云", "⛅", "partly"),
    ("cloudy", "多云", "⛅", "partly"),
    ("clear", "晴朗", "☀️", "sun"),
    ("sunny", "晴", "☀️", "sun"),
]


def _has_chinese(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def resolve_weather_desc_and_icon(desc_en: str, desc_zh: str = "") -> tuple[str, str]:
    """根据英文/中文描述解析出友好的中文短语与 Emoji 图标。"""
    desc, icon, _kind = resolve_weather(desc_en, desc_zh)
    return desc, icon


def resolve_weather(desc_en: str, desc_zh: str = "") -> tuple[str, str, str]:
    """返回 (中文描述, Emoji, 矢量图标种类)。"""
    # 若 API 返回的所谓中文里不含中文字符（wttr.in 缺字典时原样回填英文），视为无中文
    clean_zh = desc_zh.strip() if desc_zh and _has_chinese(desc_zh) else ""
    clean_en = (desc_en or "").strip().lower()

    icon, kind = "⛅", "partly"
    matched_zh = clean_zh
    for kw, zh_word, ico, knd in KEYWORD_MAP:
        if kw in clean_en:
            icon, kind = ico, knd
            if not matched_zh:
                matched_zh = zh_word
            break

    if not matched_zh:
        fallback = desc_en.strip()
        if fallback:
            titled = fallback.title()
            matched_zh = titled if len(titled) <= 12 else titled[:10] + "…"
        else:
            matched_zh = "晴"
    return matched_zh, icon, kind


def temp_to_color(temp_c: float) -> str:
    """按气温高低返回 iOS/macOS 风格的语义色彩。"""
    if temp_c <= 0:
        return "#38BDF8"  # 冰蓝
    if temp_c <= 12:
        return "#0EA5E9"  # 凉爽青蓝
    if temp_c <= 26:
        return "#10B981"  # 舒适绿
    if temp_c <= 32:
        return "#F59E0B"  # 暖温橙黄
    return "#EF4444"      # 酷热红


_WIND_ZH = {
    "N": "北风", "NNE": "东北偏北", "NE": "东北风", "ENE": "东北偏东",
    "E": "东风", "ESE": "东南偏东", "SE": "东南风", "SSE": "东南偏南",
    "S": "南风", "SSW": "西南偏南", "SW": "西南风", "WSW": "西南偏西",
    "W": "西风", "WNW": "西北偏西", "NW": "西北风", "NNW": "西北偏北",
}
_WIND_16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def wind_dir_to_zh(direction: str) -> str:
    """16方位英文风向简写转换为中文。"""
    d = direction.upper().strip()
    return _WIND_ZH.get(d, d or "微风")


def wind_deg_to_zh(deg: float | None) -> str:
    """风向角（0~360，来向）转中文方位。"""
    if deg is None:
        return "微风"
    return wind_dir_to_zh(_WIND_16[int(round(float(deg) / 22.5)) % 16])


def _local_is_day() -> bool:
    return 6 <= datetime.datetime.now().hour < 18


_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def weekday_label(date_str: str, today: datetime.date | None = None) -> str:
    """'2026-10-27' -> '今天' / '明天' / '周三'。"""
    try:
        d = datetime.date.fromisoformat(date_str[:10])
    except ValueError:
        return date_str
    delta = (d - (today or datetime.date.today())).days
    if delta == 0:
        return "今天"
    if delta == 1:
        return "明天"
    return _WEEKDAYS[d.weekday()]


def _om_daily(daily: dict[str, Any]) -> list[dict[str, Any]]:
    dates = daily.get("time") or []
    codes = daily.get("weather_code") or []
    maxs = daily.get("temperature_2m_max") or []
    mins = daily.get("temperature_2m_min") or []
    pops = daily.get("precipitation_probability_max") or []
    out = []
    for i, d in enumerate(dates):
        if i >= len(maxs) or i >= len(mins) or maxs[i] is None or mins[i] is None:
            continue
        code = int(codes[i]) if i < len(codes) and codes[i] is not None else 0
        cond, _icon, kind = WMO_CODE_MAP.get(code, ("晴", "☀️", "sun"))
        pop = pops[i] if i < len(pops) and pops[i] is not None else None
        out.append({"date": d, "label": weekday_label(d), "kind": kind, "condition": cond,
                    "max": float(maxs[i]), "min": float(mins[i]),
                    "pop": int(pop) if pop is not None else None})
    return out


def _om_hourly(hourly: dict[str, Any], cur_time: str, count: int = 8, step: int = 3) -> list[dict[str, Any]]:
    """从当前整点起，每 step 小时取一点，共 count 点（默认未来 24 小时，每 3 小时）。"""
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    codes = hourly.get("weather_code") or []
    days = hourly.get("is_day") or []
    start_key = (cur_time or "")[:13]  # 'YYYY-MM-DDTHH'
    start = next((i for i, tm in enumerate(times) if tm[:13] >= start_key), 0) if start_key else 0
    out = []
    for i in range(start, len(times), step):
        if len(out) >= count or i >= len(temps) or temps[i] is None:
            break
        code = int(codes[i]) if i < len(codes) and codes[i] is not None else 0
        _c, _e, kind = WMO_CODE_MAP.get(code, ("晴", "☀️", "sun"))
        out.append({"time": times[i][11:16], "temp": float(temps[i]), "kind": kind,
                    "is_day": bool(days[i]) if i < len(days) and days[i] is not None else True})
    return out


def _wttr_forecast(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    daily, hourly = [], []
    now = datetime.datetime.now()
    for day in data.get("weather") or []:
        hrs = day.get("hourly") or []
        noon = hrs[4] if len(hrs) > 4 else (hrs[0] if hrs else {})
        d_en = ((noon.get("weatherDesc") or [{}])[0]).get("value", "")
        d_zh = ((noon.get("lang_zh") or [{}])[0]).get("value", "")
        cond, _icon, kind = resolve_weather(d_en, d_zh)
        pops = [int(h.get("chanceofrain", 0) or 0) for h in hrs]
        date = day.get("date", "")
        try:
            daily.append({"date": date, "label": weekday_label(date), "kind": kind, "condition": cond,
                          "max": float(day["maxtempC"]), "min": float(day["mintempC"]),
                          "pop": max(pops) if pops else None})
        except (KeyError, ValueError):
            continue
        for h in hrs:
            try:
                hh = int(h.get("time", "0")) // 100
                stamp = datetime.datetime.fromisoformat(date) + datetime.timedelta(hours=hh)
            except ValueError:
                continue
            if stamp < now - datetime.timedelta(hours=1.5) or len(hourly) >= 8:
                continue
            en = ((h.get("weatherDesc") or [{}])[0]).get("value", "")
            zh = ((h.get("lang_zh") or [{}])[0]).get("value", "")
            _c, _e, knd = resolve_weather(en, zh)
            hourly.append({"time": f"{hh:02d}:00", "temp": float(h.get("tempC", 0)), "kind": knd,
                           "is_day": 6 <= hh < 18})
    return daily, hourly


def get_weather_radar_url(info: dict[str, Any]) -> str:
    """生成对应经纬度或城市的精确气象雷达 / 逐小时天气动态网页链接。"""
    lat = info.get("latitude")
    lon = info.get("longitude")
    city = str(info.get("city") or "").strip()
    if lat is not None and lon is not None:
        try:
            flat, flon = float(lat), float(lon)
            if abs(flat) > 0.001 or abs(flon) > 0.001:
                return f"https://www.windy.com/?radar,{flat:.4f},{flon:.4f},9"
        except (ValueError, TypeError):
            pass
    if city and city not in ("当前位置", "当地", "??"):
        return f"https://www.windy.com/?radar,{urllib.parse.quote(city)}"
    return "https://www.windy.com/?radar"


def parse_wttr_json(data: dict[str, Any]) -> dict[str, Any]:
    """解析 wttr.in 的 JSON 数据结构，提取标准指标。"""
    conds = data.get("current_condition") or [{}]
    cur = conds[0] if conds else {}

    areas = data.get("nearest_area") or [{}]
    area = areas[0] if areas else {}

    area_names = area.get("areaName") or [{}]
    city_name = area_names[0].get("value", "") if area_names else ""
    country_names = area.get("country") or [{}]
    country_name = country_names[0].get("value", "") if country_names else ""

    temp_c = float(cur.get("temp_C", 20.0))
    feels_c = float(cur.get("FeelsLikeC", temp_c))
    humidity = int(cur.get("humidity", 50))
    visibility_km = float(cur.get("visibility", 10.0))
    uv_index = int(cur.get("uvIndex", 1))

    descs_en = cur.get("weatherDesc") or [{}]
    desc_en = descs_en[0].get("value", "") if descs_en else ""
    descs_zh = cur.get("lang_zh") or [{}]
    desc_zh = descs_zh[0].get("value", "") if descs_zh else ""
    condition, icon, kind = resolve_weather(desc_en, desc_zh)

    weather_days = data.get("weather") or [{}]
    day0 = weather_days[0] if weather_days else {}
    max_temp = float(day0.get("maxtempC", temp_c))
    min_temp = float(day0.get("mintempC", temp_c))

    wind_speed = cur.get("windspeedKmph", "10")
    wind_dir = wind_dir_to_zh(cur.get("winddir16Point", ""))
    daily, hourly = _wttr_forecast(data)

    lat_val = None
    try:
        if area.get("latitude") is not None:
            lat_val = float(area["latitude"])
    except (ValueError, TypeError):
        lat_val = None

    lon_val = None
    try:
        if area.get("longitude") is not None:
            lon_val = float(area["longitude"])
    except (ValueError, TypeError):
        lon_val = None

    info_dict = {
        "daily": daily,
        "hourly": hourly,
        "city": city_name or "当地",
        "country": country_name,
        "temp_c": temp_c,
        "feels_like_c": feels_c,
        "condition": condition,
        "icon": icon,
        "kind": kind,
        "is_day": _local_is_day(),
        "humidity": humidity,
        "wind_speed_kmh": float(wind_speed) if str(wind_speed).replace(".", "", 1).isdigit() else 10.0,
        "wind_dir": wind_dir,
        "visibility_km": visibility_km,
        "uv_index": uv_index,
        "max_temp_c": max_temp,
        "min_temp_c": min_temp,
        "latitude": lat_val,
        "longitude": lon_val,
    }
    info_dict["radar_url"] = get_weather_radar_url(info_dict)
    return info_dict


def parse_open_meteo_json(
    forecast_data: dict[str, Any],
    city_name: str = "",
) -> dict[str, Any]:
    """解析 Open-Meteo 的 JSON 数据结构。"""
    cur = forecast_data.get("current") or {}
    daily = forecast_data.get("daily") or {}

    temp_c = float(cur.get("temperature_2m", 20.0))
    feels_c = float(cur.get("apparent_temperature", temp_c))
    humidity = int(cur.get("relative_humidity_2m", 50))
    wind_speed = float(cur.get("wind_speed_10m", 10.0))
    w_code = int(cur.get("weather_code", 0))
    vis_m = cur.get("visibility")
    visibility_km = float(vis_m) / 1000.0 if vis_m is not None else 10.0

    cond_zh, icon, kind = WMO_CODE_MAP.get(w_code, ("晴", "☀️", "sun"))

    max_temps = daily.get("temperature_2m_max") or [temp_c]
    min_temps = daily.get("temperature_2m_min") or [temp_c]
    max_temp = float(max_temps[0]) if max_temps else temp_c
    min_temp = float(min_temps[0]) if min_temps else temp_c

    lat_val = None
    try:
        if forecast_data.get("latitude") is not None:
            lat_val = float(forecast_data["latitude"])
    except (ValueError, TypeError):
        lat_val = None

    lon_val = None
    try:
        if forecast_data.get("longitude") is not None:
            lon_val = float(forecast_data["longitude"])
    except (ValueError, TypeError):
        lon_val = None

    info_dict = {
        "daily": _om_daily(daily),
        "hourly": _om_hourly(forecast_data.get("hourly") or {}, str(cur.get("time") or "")),
        "city": city_name or "当前位置",
        "country": "",
        "temp_c": temp_c,
        "feels_like_c": feels_c,
        "condition": cond_zh,
        "icon": icon,
        "kind": kind,
        "is_day": bool(cur.get("is_day", 1)),
        "humidity": humidity,
        "wind_speed_kmh": wind_speed,
        "wind_dir": wind_deg_to_zh(cur.get("wind_direction_10m")),
        "visibility_km": visibility_km,
        "uv_index": 3,
        "max_temp_c": max_temp,
        "min_temp_c": min_temp,
        "latitude": lat_val,
        "longitude": lon_val,
    }
    info_dict["radar_url"] = get_weather_radar_url(info_dict)
    return info_dict


def weather_info_to_tiles(info: dict[str, Any]) -> list[dict[str, Any]]:
    """将天气信息字典归一化为标准的 Tile 数据列表。"""
    temp_c = info["temp_c"]
    temp_str = f"{int(round(temp_c))}°"
    cond = info["condition"]
    city = info["city"]
    color = temp_to_color(temp_c)

    # 气温比率：标尺 [-10°C, 40°C] -> [0.0, 1.0]
    temp_ratio = max(0.0, min(1.0, (temp_c - (-10.0)) / 50.0))

    t_temp = make_tile(
        id="weather:temp",
        source="weather",
        name=city,
        ratio=temp_ratio,
        center_text=temp_str,
        sub_text=cond,
        color=color,
        kind="ring",
        status="ok",
        weather_info=info,
    )

    hum = info["humidity"]
    hum_ratio = max(0.0, min(1.0, hum / 100.0))
    feels_str = f"体感 {int(round(info['feels_like_c']))}°"
    t_humidity = make_tile(
        id="weather:humidity",
        source="weather",
        name="湿度",
        ratio=hum_ratio,
        center_text=f"{hum}%",
        sub_text=feels_str,
        color="#06B6D4",
        kind="ring",
        status="ok",
        weather_info=info,
    )

    wind_d = info.get("wind_dir", "微风")
    wind_s = int(round(info.get("wind_speed_kmh", 10.0)))
    t_wind = make_tile(
        id="weather:wind",
        source="weather",
        name="风向",
        ratio=min(1.0, max(0.1, wind_s / 60.0)),
        center_text=wind_d[:2],
        sub_text=f"{wind_s} km/h",
        color="#8B5CF6",
        kind="ring",
        status="ok",
        weather_info=info,
    )

    return [t_temp, t_humidity, t_wind]


# ---------------------------------------------------------------- 网络拉取

_LOC_TTL_SEC = 6 * 3600
_LOC_CACHE: dict[str, tuple[float, float, float, str]] = {}  # key -> (ts, lat, lon, name)


def fetch_wttr(city: str = "", timeout: float = 6.0) -> dict[str, Any]:
    """从 wttr.in 拉取 JSON 数据。"""
    encoded_city = urllib.parse.quote(city.strip()) if city.strip() else ""
    url = f"https://wttr.in/{encoded_city}?format=j1&lang=zh"
    headers = {
        "User-Agent": "curl/7.68.0",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    info = parse_wttr_json(data)
    if city.strip():
        info["city"] = city.strip()
    return info


def _locate(city: str, timeout: float) -> tuple[float, float, str]:
    """城市名 -> 经纬度（带 6 小时内存缓存）；城市留空则按 IP 定位。"""
    key = city.strip()
    hit = _LOC_CACHE.get(key)
    if hit and time.time() - hit[0] < _LOC_TTL_SEC:
        return hit[1], hit[2], hit[3]

    headers = {"User-Agent": "AnyBar/1.0"}
    if key:
        geo_url = ("https://geocoding-api.open-meteo.com/v1/search?name="
                   f"{urllib.parse.quote(key)}&count=1&language=zh")
        with urllib.request.urlopen(urllib.request.Request(geo_url, headers=headers),
                                    timeout=timeout) as resp:
            results = json.loads(resp.read().decode("utf-8")).get("results")
        if not results:
            raise ValueError(f"未找到城市：{key}")
        lat, lon = results[0]["latitude"], results[0]["longitude"]
        name = results[0].get("name", key)
    else:
        lat, lon, name = None, None, None
        try:
            req = urllib.request.Request("https://ipwho.is/?lang=zh-CN", headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("success") is True and data.get("latitude") is not None:
                lat = float(data["latitude"])
                lon = float(data["longitude"])
                name = str(data.get("city") or "当前位置")
        except Exception:
            pass

        if lat is None or lon is None:
            try:
                req = urllib.request.Request("https://freeipapi.com/api/json", headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    ip_data = json.loads(resp.read().decode("utf-8"))
                if ip_data.get("latitude") is not None and ip_data.get("longitude") is not None:
                    lat = float(ip_data["latitude"])
                    lon = float(ip_data["longitude"])
                    name = str(ip_data.get("cityName") or "当前位置")
            except Exception:
                pass

        if lat is None or lon is None:
            raise RuntimeError("IP 定位失败")

    _LOC_CACHE[key] = (time.time(), lat, lon, name)
    return lat, lon, name


def fetch_open_meteo(city: str = "", timeout: float = 6.0) -> dict[str, Any]:
    """从 Open-Meteo 拉取天气数据。"""
    lat, lon, res_city = _locate(city, min(4.0, timeout))
    fc_url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,"
        "weather_code,wind_speed_10m,wind_direction_10m,visibility"
        "&hourly=temperature_2m,weather_code,is_day"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&forecast_days=7&timezone=auto"
    )
    req = urllib.request.Request(fc_url, headers={"User-Agent": "AnyBar/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        fc_data = json.loads(resp.read().decode("utf-8"))
    return parse_open_meteo_json(fc_data, city_name=res_city)


def fetch_weather_info(city: str = "", timeout: float = 6.0) -> dict[str, Any]:
    """并行请求两个数据源：优先采用 Open-Meteo，失败才用 wttr.in，总耗时 ≈ 较快成功者。"""
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="weather")
    try:
        f_main = pool.submit(fetch_open_meteo, city, timeout)
        f_backup = pool.submit(fetch_wttr, city, timeout)
        try:
            return f_main.result()
        except Exception as main_err:
            try:
                return f_backup.result()
            except Exception as backup_err:
                raise RuntimeError(f"天气获取失败: {main_err}; {backup_err}") from backup_err
    finally:
        pool.shutdown(wait=False)


# ---------------------------------------------------------------- 磁盘缓存

def _cache_path():
    from app.core import config as config_mod
    return config_mod.CONFIG_DIR / CACHE_FILENAME


def save_cache(city: str, info: dict[str, Any]) -> None:
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"city": city.strip(), "ts": time.time(), "info": info},
                                   ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def load_cached_tiles(cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], float] | None:
    """启动时读取缓存（城市配置一致且未过期），返回 (tiles, 缓存时间戳)。"""
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        want_city = str(((cfg.get("sources") or {}).get("weather") or {}).get("city") or "").strip()
        ts = float(data.get("ts", 0))
        if str(data.get("city") or "").strip() != want_city:
            return None
        if time.time() - ts > CACHE_MAX_AGE_SEC:
            return None
        info = data["info"]
        return weather_info_to_tiles(info), ts
    except (OSError, ValueError, KeyError, TypeError):
        return None


@register(
    SourceInfo(
        id="weather",
        title="当地实时天气 (气温 / 状况 / 湿度)",
        description="实时采集所在地或指定城市的气温、天气状况、湿度与体感",
        kind="remote",
        default_interval_sec=900,
        min_interval_sec=60,
        needs_credentials=False,
        cache_loader=load_cached_tiles,
    )
)
def fetch_weather_tiles(cfg: dict[str, Any], timeout: float = 6.0) -> list[dict[str, Any]]:
    """拉取天气数据并返回 3 个标准 Tile。"""
    src_cfg = (cfg.get("sources") or {}).get("weather") or {}
    city = str(src_cfg.get("city") or "").strip()

    info = fetch_weather_info(city=city, timeout=timeout)
    if not info:
        raise RuntimeError("未获取到有效天气信息")
    save_cache(city, info)
    return weather_info_to_tiles(info)
