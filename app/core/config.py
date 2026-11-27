import base64
import copy
import json
import sys
from pathlib import Path

from app.platform import win32_utils

if getattr(sys, "frozen", False):
    CONFIG_DIR = Path(sys.executable).resolve().parent / "data"
else:
    CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CONFIG_FILE = CONFIG_DIR / "config.json"
UIA_CACHE_FILE = CONFIG_DIR / "uia_cache.json"

QUOTA_COLORS = ("#3B82F6", "#8B5CF6", "#F59E0B", "#10B981")

# GLM Coding Plan 自动余额查询：站点键 → API 根地址
QUOTA_SITES = {"bigmodel": "https://open.bigmodel.cn", "zai": "https://api.z.ai"}

SECRET_PREFIX = "dpapi:"


def encrypt_secret(val: str) -> str:
    """将敏感字符串（如 API Key）使用 Windows DPAPI 加密并以 dpapi: 前缀 Base64 保存。"""
    if not val or not isinstance(val, str):
        return ""
    val_str = val.strip()
    if not val_str:
        return ""
    if val_str.startswith(SECRET_PREFIX):
        return val_str
    try:
        enc_bytes = win32_utils.dpapi_protect(val_str.encode("utf-8"))
        return SECRET_PREFIX + base64.b64encode(enc_bytes).decode("ascii")
    except Exception:
        return val_str


def decrypt_secret(val: str) -> str:
    """解密敏感字符串。若非 dpapi: 前缀则视为旧版明文或用户手填明文，原样返回。"""
    if not val or not isinstance(val, str):
        return ""
    val_str = val.strip()
    if not val_str.startswith(SECRET_PREFIX):
        return val_str
    b64_str = val_str[len(SECRET_PREFIX):]
    try:
        cipher_bytes = base64.b64decode(b64_str.encode("ascii"))
        plain_bytes = win32_utils.dpapi_unprotect(cipher_bytes)
        return plain_bytes.decode("utf-8")
    except Exception:
        # 解密失败（如换机或跨用户迁移），优雅降级为空字符串
        return ""


DEFAULT_PANEL_CARDS = [
    {
        "id": "schedule",
        "name": "日程时段",
        "desc": "当前时段状态、时段进度条与全天日程列表",
        "enabled": True,
    },
    {
        "id": "todos",
        "name": "待办事项",
        "desc": "今日待办任务列表、打勾标记完成与快速新建待办",
        "enabled": True,
    },
    {
        "id": "system",
        "name": "电脑状态监控",
        "desc": "CPU 使用率、内存占用与硬盘空间余量实时监控",
        "enabled": True,
    },
    {
        "id": "quotas",
        "name": "算力与额度",
        "desc": "AI 模型套餐剩余额度、用量百分比与周期刷新",
        "enabled": True,
    },
    {
        "id": "weather",
        "name": "实时天气",
        "desc": "所在地或指定城市的天气状况、气温、湿度与体感",
        "enabled": True,
    },
    {
        "id": "dev",
        "name": "Git 仓库状态",
        "desc": "当前分支、工作区未提交改动数与一键唤起系统终端",
        "enabled": True,
    },
]


DEFAULT_CONFIG = {
    "schedule": [
        {"start": "08:00", "end": "12:00", "text": "上午 · 专注工作学习，少看手机", "note": "此时间段远离手机"},
        {"start": "12:00", "end": "14:00", "text": "午休 · 吃饭散步", "note": "饭后走 15 分钟"},
        {"start": "14:00", "end": "18:00", "text": "下午 · 深度工作", "note": "每小时起身活动"},
        {"start": "18:00", "end": "23:59", "text": "晚间 · 复盘阅读", "note": "23:30 前放下手机"},
    ],
    "defaultText": "自由时间 · 注意休息",
    "todos": [
        {"time": "14:00", "title": "示例待办 · 写日报", "note": "下班前完成", "done": False},
        {"time": "20:00", "title": "示例待办 · 阅读半小时", "note": "", "done": False},
    ],
    "quotas": [
        {"name": "Cursor", "used": 340, "limit": 500, "unit": "req",
         "color": QUOTA_COLORS[0]},
        {"name": "DeepSeek", "balance": "¥18.5", "status": "ok",
         "color": QUOTA_COLORS[1]},
    ],
    "quotaApi": {
        "enabled": False,       # 是否启用自动查询
        "showOnBar": True,      # 是否在常驻条额度视图显示 GLM 圆环
        "base": "bigmodel",     # 站点键：bigmodel=智谱国内 / zai=Z.ai 国际
        "scope": "personal",    # 套餐范围：personal=个人 / team=团队
        "orgId": "",            # 团队组织 ID（scope=team 时使用，可自动发现）
        "projectId": "",        # 团队项目 ID（同上）
        "apiKey": "",           # GLM Coding Plan API Key（仅存本机，落盘 DPAPI 加密）
        "intervalMin": 10,      # 轮询间隔（分钟）
        "source": "glm",        # 数据源：glm=智谱直连 / magpie=本机 Magpie 聚合网关
        "magpieUrl": "http://127.0.0.1:3425",
        "magpieProviders": [],  # 勾选展示的 Magpie 渠道（空列表表示全部有数据的渠道）
    },
    "style": {
        "themeMode": "auto",    # "auto"=跟随系统 / "light"=浅色 / "dark"=深色
        "fontFamily": "Microsoft YaHei UI",
        "fontSize": 10,
        "bold": True,
        "autoColor": True,
        "darkThemeColor": "#F9FAFB",
        "lightThemeColor": "#111827",
        "rightColor": "#38BDF8",
        "scheduleBarColor": "#F59E0B",
        "barView": "schedule",
        "bgMode": "glass",
        "bgColor": "#1F1F1F",
        "scrollSpeed": 30,
        "gapPx": 90,
        "scrollPauseSec": 8,
        "rightMode": "scroll",
        "width": 330,
        "iconSlot": "auto",
        "displayMode": "full",  # "full"=标准全量长条 / "capsule"=微型双列胶囊模式
        "capsuleLeft": "weather",   # "weather" / "cpu" / "ram" / "quota" / "net" / "dev"
        "capsuleRight": "cpu",      # "cpu" / "ram" / "weather" / "quota" / "net" / "dev"
    },
    "sources": {
        "quota": {"enabled": True, "intervalSec": 600},
        "system": {"enabled": True, "intervalSec": 2},
        "weather": {"enabled": True, "intervalSec": 900, "city": ""},
        "dev": {"enabled": True, "intervalSec": 5, "repoPath": ""},
    },
    "panelCards": copy.deepcopy(DEFAULT_PANEL_CARDS),
}


def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {}
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    needs_migration = False

    for section in ("schedule", "todos"):
        if isinstance(data.get(section), list):
            cfg[section] = data[section]

    if isinstance(data.get("quotas"), list):
        qs = []
        for q in data["quotas"]:
            if isinstance(q, dict):
                item = copy.copy(q)
                k = item.get("apiKey")
                if isinstance(k, str) and k.strip():
                    k_strip = k.strip()
                    if k_strip.startswith(SECRET_PREFIX):
                        item["apiKey"] = decrypt_secret(k_strip)
                    elif item.get("provider") != "magpie":
                        needs_migration = True
                        item["apiKey"] = k_strip
                qs.append(item)
        cfg["quotas"] = qs

    qa = cfg["quotaApi"]
    if isinstance(data.get("quotaApi"), dict):
        src = data["quotaApi"]
        qa["enabled"] = bool(src.get("enabled", qa["enabled"]))
        qa["showOnBar"] = bool(src.get("showOnBar", qa["showOnBar"]))
        base = str(src.get("base", "") or "")
        if base in QUOTA_SITES:
            qa["base"] = base
        key = src.get("apiKey")
        if isinstance(key, str):
            k_strip = key.strip()
            if k_strip.startswith(SECRET_PREFIX):
                qa["apiKey"] = decrypt_secret(k_strip)
            elif k_strip:
                needs_migration = True
                qa["apiKey"] = k_strip
            else:
                qa["apiKey"] = ""
        if str(src.get("scope", "")) == "team":
            qa["scope"] = "team"
        for src_key, dst_key in (("orgId", "orgId"), ("projectId", "projectId")):
            v = src.get(src_key)
            if isinstance(v, str):
                qa[dst_key] = v.strip()
        try:
            interval = int(src.get("intervalMin", qa["intervalMin"]))
        except (TypeError, ValueError):
            interval = qa["intervalMin"]
        qa["intervalMin"] = max(1, min(720, interval))
        if str(src.get("source", "")) in ("glm", "magpie"):
            qa["source"] = str(src["source"])
        m_url = src.get("magpieUrl")
        if isinstance(m_url, str) and m_url.strip():
            qa["magpieUrl"] = m_url.strip()
        m_provs = src.get("magpieProviders")
        if isinstance(m_provs, list):
            qa["magpieProviders"] = [str(x).strip() for x in m_provs if str(x).strip()]

    for t in cfg["todos"]:
        if isinstance(t, dict):
            t.setdefault("done", False)

    style = cfg["style"]
    if isinstance(data.get("style"), dict):
        for k, v in data["style"].items():
            if k in style:
                style[k] = v
    if style.get("themeMode") not in ("auto", "light", "dark"):
        style["themeMode"] = "auto"
    if style.get("bgMode") == "transparent":
        style["bgMode"] = "glass"
    if style.get("fontFamily") in ("黑体", "SimHei", "Microsoft YaHei"):
        style["fontFamily"] = "Microsoft YaHei UI"
    if style.get("barView") == "tiles":
        style["barView"] = "quota"
    if style.get("displayMode") not in ("full", "capsule"):
        style["displayMode"] = "full"
    valid_slots = ("weather", "cpu", "ram", "quota", "net", "dev")
    if style.get("capsuleLeft") not in valid_slots:
        style["capsuleLeft"] = "weather"
    if style.get("capsuleRight") not in valid_slots:
        style["capsuleRight"] = "cpu" 

    if isinstance(data.get("sources"), dict):
        for s_id, s_val in data["sources"].items():
            if isinstance(s_val, dict):
                cfg["sources"].setdefault(s_id, {})
                cfg["sources"][s_id].update(s_val)
                for sec_key in ("apiKey", "sessionToken"):
                    if sec_key in cfg["sources"][s_id]:
                        val = cfg["sources"][s_id][sec_key]
                        if isinstance(val, str) and val.strip():
                            v_strip = val.strip()
                            if v_strip.startswith(SECRET_PREFIX):
                                cfg["sources"][s_id][sec_key] = decrypt_secret(v_strip)
                            else:
                                needs_migration = True
                                cfg["sources"][s_id][sec_key] = v_strip

    if isinstance(data.get("panelCards"), list):
        loaded_cards = []
        seen_ids = set()
        for item in data["panelCards"]:
            if isinstance(item, dict) and "id" in item:
                cid = str(item["id"]).strip()
                if cid == "header":
                    cid = "schedule"
                elif cid == "tiles":
                    cid = "quotas"
                if cid and cid not in seen_ids and cid != "music":
                    seen_ids.add(cid)
                    def_item = next((x for x in DEFAULT_PANEL_CARDS if x["id"] == cid), None)
                    name = str(item.get("name") or (def_item["name"] if def_item else cid))
                    desc = str(item.get("desc") or (def_item.get("desc", "") if def_item else ""))
                    enabled = bool(item.get("enabled", True))
                    c_dict = {"id": cid, "name": name, "enabled": enabled}
                    if desc:
                        c_dict["desc"] = desc
                    loaded_cards.append(c_dict)
        for def_item in DEFAULT_PANEL_CARDS:
            if def_item["id"] not in seen_ids:
                loaded_cards.append(copy.deepcopy(def_item))
                seen_ids.add(def_item["id"])
        cfg["panelCards"] = loaded_cards

    if needs_migration and CONFIG_FILE.exists():
        try:
            save_config(cfg)
        except OSError:
            pass

    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    disk_cfg = copy.deepcopy(cfg)
    if "quotaApi" in disk_cfg and isinstance(disk_cfg["quotaApi"], dict):
        k = disk_cfg["quotaApi"].get("apiKey")
        if isinstance(k, str) and k.strip():
            disk_cfg["quotaApi"]["apiKey"] = encrypt_secret(k)
    if "quotas" in disk_cfg and isinstance(disk_cfg["quotas"], list):
        for q in disk_cfg["quotas"]:
            if isinstance(q, dict) and q.get("provider") != "magpie":
                k = q.get("apiKey")
                if isinstance(k, str) and k.strip():
                    q["apiKey"] = encrypt_secret(k)
    if "sources" in disk_cfg and isinstance(disk_cfg["sources"], dict):
        for s_id, s_val in disk_cfg["sources"].items():
            if isinstance(s_val, dict):
                for sec_key in ("apiKey", "sessionToken"):
                    k = s_val.get(sec_key)
                    if isinstance(k, str) and k.strip():
                        s_val[sec_key] = encrypt_secret(k)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(disk_cfg, f, ensure_ascii=False, indent=2)


def load_uia_cache():
    try:
        with open(UIA_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        v = data.get("icon_right")
        if isinstance(v, int) and v > 0:
            return v
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return None


def save_uia_cache(icon_right: int) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(UIA_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"icon_right": int(icon_right)}, f)
    except OSError:
        pass


def _parse_hm(value: str):
    h, m = map(int, value.split(":"))
    return h * 60 + m


def current_schedule(cfg: dict, now):
    minutes = now.hour * 60 + now.minute
    for item in cfg["schedule"]:
        try:
            start_min = _parse_hm(item.get("start", "0:0"))
            end_min = _parse_hm(item.get("end", "23:59"))
        except ValueError:
            continue
        if start_min <= end_min:
            if start_min <= minutes < end_min:
                return item
        elif minutes >= start_min or minutes < end_min:
            return item
    return None


def next_schedule(cfg: dict, now):
    minutes = now.hour * 60 + now.minute
    candidates = []
    for item in cfg["schedule"]:
        try:
            start_min = _parse_hm(item.get("start", "0:0"))
            end_min = _parse_hm(item.get("end", "23:59"))
        except ValueError:
            continue
        ongoing_overnight = start_min > end_min and minutes < end_min
        if start_min > minutes and not ongoing_overnight:
            candidates.append((start_min, item))
    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1], candidates[0][0] - minutes
    for item in cfg["schedule"]:
        try:
            start_min = _parse_hm(item.get("start", "0:0"))
        except ValueError:
            continue
        return item, (start_min + 1440) - minutes
    return None, None


def schedule_progress(cfg: dict, now) -> float:
    cur = current_schedule(cfg, now)
    if not cur:
        return 0.0
    minutes = now.hour * 60 + now.minute
    try:
        start_min = _parse_hm(cur.get("start", "0:0"))
        end_min = _parse_hm(cur.get("end", "23:59"))
    except ValueError:
        return 0.0
    if start_min == end_min:
        return 1.0
    if start_min < end_min:
        passed = minutes - start_min
        total = end_min - start_min
    else:
        passed = (minutes - start_min) % 1440
        total = (1440 - start_min) + end_min
    if passed <= 0:
        return 0.0
    return max(0.0, min(1.0, passed / total))
