import copy
import json
from datetime import datetime

import pytest

from app.core import config


def _dt(h, m):
    return datetime(2026, 10, 20, h, m)


def _cfg(*items):
    return {"schedule": list(items), "todos": [], "style": {}}


class TestCurrentSchedule:
    def test_hits_middle_of_range(self):
        cfg = _cfg({"start": "08:00", "end": "12:00"})
        assert config.current_schedule(cfg, _dt(9, 30)) == cfg["schedule"][0]

    def test_start_boundary_inclusive(self):
        cfg = _cfg({"start": "08:00", "end": "12:00"})
        assert config.current_schedule(cfg, _dt(8, 0)) == cfg["schedule"][0]

    def test_end_boundary_exclusive(self):
        cfg = _cfg({"start": "08:00", "end": "12:00"})
        assert config.current_schedule(cfg, _dt(12, 0)) is None

    def test_gap_returns_none(self):
        cfg = _cfg({"start": "08:00", "end": "12:00"}, {"start": "14:00", "end": "18:00"})
        assert config.current_schedule(cfg, _dt(13, 0)) is None

    def test_full_day(self):
        cfg = _cfg({"start": "08:00", "end": "23:59"})
        assert config.current_schedule(cfg, _dt(23, 58)) == cfg["schedule"][0]
        assert config.current_schedule(cfg, _dt(2, 0)) is None

    def test_overnight_evening(self):
        cfg = _cfg({"start": "23:00", "end": "01:00"})
        assert config.current_schedule(cfg, _dt(23, 30)) == cfg["schedule"][0]

    def test_overnight_after_midnight(self):
        cfg = _cfg({"start": "23:00", "end": "01:00"})
        assert config.current_schedule(cfg, _dt(0, 30)) == cfg["schedule"][0]

    def test_overnight_outside(self):
        cfg = _cfg({"start": "23:00", "end": "01:00"})
        assert config.current_schedule(cfg, _dt(12, 0)) is None

    def test_invalid_time_skipped(self):
        cfg = _cfg({"start": "abc", "end": "12:00"}, {"start": "14:00", "end": "16:00"})
        assert config.current_schedule(cfg, _dt(15, 0)) == cfg["schedule"][1]

    def test_empty_schedule(self):
        assert config.current_schedule(_cfg(), _dt(9, 0)) is None


class TestNextSchedule:
    def test_next_today(self):
        cfg = _cfg({"start": "08:00", "end": "12:00"}, {"start": "14:00", "end": "18:00"})
        item, remain = config.next_schedule(cfg, _dt(10, 0))
        assert item == cfg["schedule"][1]
        assert remain == 240

    def test_wraps_to_first_tomorrow(self):
        cfg = _cfg({"start": "08:00", "end": "12:00"})
        item, remain = config.next_schedule(cfg, _dt(20, 0))
        assert item == cfg["schedule"][0]
        assert remain == 720

    def test_overnight_ongoing_not_a_candidate(self):
        cfg = _cfg({"start": "23:00", "end": "01:00"}, {"start": "08:00", "end": "12:00"})
        item, remain = config.next_schedule(cfg, _dt(0, 30))
        assert item == cfg["schedule"][1]
        assert remain == 450

    def test_overnight_upcoming(self):
        cfg = _cfg({"start": "08:00", "end": "12:00"}, {"start": "23:00", "end": "01:00"})
        item, remain = config.next_schedule(cfg, _dt(22, 0))
        assert item == cfg["schedule"][1]
        assert remain == 60

    def test_empty_schedule(self):
        assert config.next_schedule(_cfg(), _dt(9, 0)) == (None, None)

    def test_all_invalid_skipped(self):
        cfg = _cfg({"start": "xx:yy", "end": "12:00"})
        assert config.next_schedule(cfg, _dt(9, 0)) == (None, None)


class TestScheduleProgress:
    def test_mid_progress(self):
        cfg = _cfg({"start": "08:00", "end": "12:00"})
        assert config.schedule_progress(cfg, _dt(10, 0)) == 0.5

    def test_start_zero(self):
        cfg = _cfg({"start": "08:00", "end": "12:00"})
        assert config.schedule_progress(cfg, _dt(8, 0)) == 0.0

    def test_end_full(self):
        cfg = _cfg({"start": "08:00", "end": "12:00"})
        assert config.schedule_progress(cfg, _dt(11, 59)) == 239 / 240

    def test_gap_returns_zero(self):
        cfg = _cfg({"start": "08:00", "end": "12:00"})
        assert config.schedule_progress(cfg, _dt(13, 0)) == 0.0

    def test_overnight(self):
        cfg = _cfg({"start": "23:00", "end": "01:00"})
        assert config.schedule_progress(cfg, _dt(0, 0)) == 0.5

    def test_empty_schedule(self):
        assert config.schedule_progress(_cfg(), _dt(9, 0)) == 0.0



class TestLoadConfig:
    def test_missing_file_returns_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        cfg = config.load_config()
        assert cfg["defaultText"] == config.DEFAULT_CONFIG["defaultText"]
        assert cfg["schedule"] == config.DEFAULT_CONFIG["schedule"]

    def test_corrupt_json_returns_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text("{broken", encoding="utf-8")
        cfg = config.load_config()
        assert cfg["schedule"] == config.DEFAULT_CONFIG["schedule"]

    def test_unknown_style_key_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"style": {"fontSize": 12, "hackKey": "x"}}), encoding="utf-8")
        cfg = config.load_config()
        assert cfg["style"]["fontSize"] == 12
        assert "hackKey" not in cfg["style"]

    def test_legacy_bgmode_migrated(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"style": {"bgMode": "transparent"}}), encoding="utf-8")
        cfg = config.load_config()
        assert cfg["style"]["bgMode"] == "glass"

    def test_legacy_font_migrated(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"style": {"fontFamily": "SimHei"}}), encoding="utf-8")
        cfg = config.load_config()
        assert cfg["style"]["fontFamily"] == "Microsoft YaHei UI"

    def test_todo_done_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"todos": [{"time": "14:00", "title": "x"}]}), encoding="utf-8")
        cfg = config.load_config()
        assert cfg["todos"][0]["done"] is False

    def test_bad_schedule_type_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"schedule": "not-a-list"}), encoding="utf-8")
        cfg = config.load_config()
        assert cfg["schedule"] == config.DEFAULT_CONFIG["schedule"]


class TestQuotasAndIconSlot:
    def test_default_quotas_loaded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        cfg = config.load_config()
        assert cfg["quotas"] == config.DEFAULT_CONFIG["quotas"]
        assert len(cfg["quotas"]) == 2

    def test_quotas_overridden(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        custom = [{"name": "Claude", "used": 10, "limit": 20, "unit": "h"}]
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"quotas": custom}), encoding="utf-8")
        cfg = config.load_config()
        assert cfg["quotas"] == custom

    def test_bad_quota_entries_filtered(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"quotas": [{"name": "X"}, "junk", 5]}), encoding="utf-8")
        cfg = config.load_config()
        assert cfg["quotas"] == [{"name": "X"}]

    def test_bad_quotas_type_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"quotas": "nope"}), encoding="utf-8")
        cfg = config.load_config()
        assert cfg["quotas"] == config.DEFAULT_CONFIG["quotas"]

    def test_icon_slot_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        cfg = config.load_config()
        assert cfg["style"]["iconSlot"] == "auto"

    def test_icon_slot_persisted(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"style": {"iconSlot": "flame"}}), encoding="utf-8")
        cfg = config.load_config()
        assert cfg["style"]["iconSlot"] == "flame"


class TestSaveUiaCache:
    def test_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "UIA_CACHE_FILE", tmp_path / "uia_cache.json")
        config.save_uia_cache(2650)
        assert config.load_uia_cache() == 2650

    def test_missing_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "UIA_CACHE_FILE", tmp_path / "uia_cache.json")
        assert config.load_uia_cache() is None

    def test_nonpositive_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "UIA_CACHE_FILE", tmp_path / "uia_cache.json")
        tmp_path.joinpath("uia_cache.json").write_text(json.dumps({"icon_right": -5}))
        assert config.load_uia_cache() is None

class TestBarView:
    def test_default_is_schedule(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        cfg = config.load_config()
        assert cfg["style"]["barView"] == "schedule"

    def test_saved_quota_view_preserved(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"style": {"barView": "quota"}}), encoding="utf-8")
        cfg = config.load_config()
        assert cfg["style"]["barView"] == "quota"

    def test_saved_system_view_preserved(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"style": {"barView": "system"}}), encoding="utf-8")
        cfg = config.load_config()
        assert cfg["style"]["barView"] == "system"

    def test_saved_tiles_view_migrated_to_quota(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"style": {"barView": "tiles"}}), encoding="utf-8")
        cfg = config.load_config()
        assert cfg["style"]["barView"] == "quota"

class TestQuotaApiConfig:
    def test_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        cfg = config.load_config()
        assert cfg["quotaApi"] == config.DEFAULT_CONFIG["quotaApi"]
        assert cfg["quotaApi"]["enabled"] is False
        assert cfg["quotaApi"]["base"] == "bigmodel"

    def test_known_keys_merged(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"quotaApi": {"enabled": True, "base": "zai",
                                     "apiKey": " k123 ",
                                     "intervalMin": 30}}), encoding="utf-8")
        cfg = config.load_config()
        qa = cfg["quotaApi"]
        assert qa["enabled"] is True
        assert qa["base"] == "zai"
        assert qa["apiKey"] == "k123"
        assert qa["intervalMin"] == 30

    def test_unknown_keys_and_bad_base_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"quotaApi": {"base": "evil.example",
                                     "hack": 1,
                                     "apiKey": None}}), encoding="utf-8")
        cfg = config.load_config()
        qa = cfg["quotaApi"]
        assert qa["base"] == "bigmodel"
        assert "hack" not in qa
        assert qa["apiKey"] == ""

    def test_interval_clamped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"quotaApi": {"intervalMin": 9999}}), encoding="utf-8")
        cfg = config.load_config()
        assert cfg["quotaApi"]["intervalMin"] == 720
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"quotaApi": {"intervalMin": 0}}), encoding="utf-8")
        assert config.load_config()["quotaApi"]["intervalMin"] == 1

    def test_bad_type_falls_back_to_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"quotaApi": "junk"}), encoding="utf-8")
        cfg = config.load_config()
        assert cfg["quotaApi"] == config.DEFAULT_CONFIG["quotaApi"]


class TestSettingsDialogTimeEditing:
    def test_normalize_time_str_variants(self):
        from app.gui.settings import _normalize_time_str
        assert _normalize_time_str("9:30", allow_empty=False) == "09:30"
        assert _normalize_time_str("16", allow_empty=False) == "16:00"
        assert _normalize_time_str("830", allow_empty=False) == "08:30"
        assert _normalize_time_str("1430", allow_empty=False) == "14:30"
        assert _normalize_time_str("09：15", allow_empty=False) == "09:15"
        assert _normalize_time_str("", allow_empty=True) == ""
        assert _normalize_time_str("--:--", allow_empty=True) == ""
        assert _normalize_time_str("", allow_empty=False, default_str="08:00") == "08:00"

    def test_simulated_keyboard_time_editing(self):
        import copy
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from app.gui.settings import SettingsDialog

        app = QApplication.instance() or QApplication([])
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["todos"] = [
            {"time": "", "title": "无时间待办", "note": "", "done": False},
            {"time": "14:00", "title": "有时间待办", "note": "", "done": False},
        ]
        previewed = []
        dlg = SettingsDialog(None, cfg, preview_callback=lambda c: previewed.append(copy.deepcopy(c)))

        # 1. 日程开始时间输入 "9:30"、结束时间输入 "16"
        row0 = dlg._sched_rows[0]
        start_edit, end_edit = row0["start"], row0["end"]
        assert start_edit.validator() is None
        assert end_edit.validator() is None

        start_edit.clear()
        QTest.keyClicks(start_edit, "9:30")
        assert start_edit.text() == "9:30"
        start_edit.editingFinished.emit()
        assert start_edit.text() == "09:30"

        end_edit.clear()
        QTest.keyClicks(end_edit, "16")
        assert end_edit.text() == "16"
        end_edit.editingFinished.emit()
        assert end_edit.text() == "16:00"

        # 2. 待办时间框：初始空待办真实文本为 ""（placeholder 为 "--:--"），可直接输入 "1430"
        todo0_time = dlg._todo_rows[0]["time"]
        assert todo0_time.validator() is None
        assert todo0_time.text() == ""
        assert todo0_time.placeholderText() == "--:--"
        QTest.keyClicks(todo0_time, "1430")
        assert todo0_time.text() == "1430"
        todo0_time.editingFinished.emit()
        assert todo0_time.text() == "14:30"

        # 3. 待办时间框清空字符串 -> 保存为 ""
        todo1_time = dlg._todo_rows[1]["time"]
        assert todo1_time.text() == "14:00"
        todo1_time.clear()
        QTest.keyClick(todo1_time, Qt.Key.Key_Return)
        todo1_time.editingFinished.emit()
        assert todo1_time.text() == ""

        dlg._collect_config()
        out = dlg.get_config()
        assert out["schedule"][0]["start"] == "09:30"
        assert out["schedule"][0]["end"] == "16:00"
        assert out["todos"][0]["time"] == "14:30"
        assert out["todos"][1]["time"] == ""
        dlg.close()

class TestQuotaApiTeamConfig:
    def test_team_fields_merged(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"quotaApi": {"scope": "team",
                                     "orgId": " org-1 ",
                                     "projectId": "proj_1"}}), encoding="utf-8")
        qa = config.load_config()["quotaApi"]
        assert qa["scope"] == "team"
        assert qa["orgId"] == "org-1"
        assert qa["projectId"] == "proj_1"

    def test_bad_scope_falls_back_personal(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"quotaApi": {"scope": "enterprise"}}), encoding="utf-8")
        assert config.load_config()["quotaApi"]["scope"] == "personal"

    def test_default_personal(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        qa = config.load_config()["quotaApi"]
        assert qa["scope"] == "personal"
        assert qa["orgId"] == "" and qa["projectId"] == ""


class TestDpapiSecrets:
    def test_encrypt_decrypt_roundtrip(self):
        secret = "sk-ant-api03-abcdef1234567890_test_key"
        cipher = config.encrypt_secret(secret)
        assert cipher.startswith(config.SECRET_PREFIX)
        assert cipher != secret
        plain = config.decrypt_secret(cipher)
        assert plain == secret

    def test_encrypt_empty_or_none(self):
        assert config.encrypt_secret("") == ""
        assert config.encrypt_secret("   ") == ""
        assert config.encrypt_secret(None) == ""
        assert config.decrypt_secret("") == ""
        assert config.decrypt_secret(None) == ""

    def test_encrypt_idempotent(self):
        secret = "my_api_key"
        cipher = config.encrypt_secret(secret)
        assert config.encrypt_secret(cipher) == cipher

    def test_decrypt_plain_backward_compatibility(self):
        # 旧版明文无 dpapi: 前缀，直接返回
        raw = "plain_api_key_123"
        assert config.decrypt_secret(raw) == raw

    def test_decrypt_corrupted_secret_graceful(self):
        # 损坏的密文不应导致崩溃，应返回空字符串
        assert config.decrypt_secret("dpapi:!!!invalid_base64!!!") == ""
        assert config.decrypt_secret("dpapi:AAAA") == ""

    def test_save_config_encrypts_on_disk_preserves_memory(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "config.json"
        monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(config, "CONFIG_FILE", cfg_file)

        raw_cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        raw_cfg["quotaApi"]["apiKey"] = "glm_super_secret_key"
        raw_cfg["quotas"] = [
            {"name": "DeepSeek", "provider": "deepseek", "apiKey": "ds_secret_key"},
            {"name": "Magpie", "provider": "magpie", "apiKey": "zcode"},
        ]

        config.save_config(raw_cfg)

        # 内存中的对象保持纯明文，完全不受污染
        assert raw_cfg["quotaApi"]["apiKey"] == "glm_super_secret_key"
        assert raw_cfg["quotas"][0]["apiKey"] == "ds_secret_key"
        assert raw_cfg["quotas"][1]["apiKey"] == "zcode"

        # 磁盘上的内容已被加密
        disk_data = json.loads(cfg_file.read_text(encoding="utf-8"))
        disk_glm_key = disk_data["quotaApi"]["apiKey"]
        disk_ds_key = disk_data["quotas"][0]["apiKey"]
        disk_mp_key = disk_data["quotas"][1]["apiKey"]

        assert disk_glm_key.startswith("dpapi:")
        assert disk_glm_key != "glm_super_secret_key"
        assert disk_ds_key.startswith("dpapi:")
        assert disk_ds_key != "ds_secret_key"
        # Magpie 渠道标识保持明文
        assert disk_mp_key == "zcode"

        # 再次从磁盘 load_config，自动解密还原为明文供业务代码使用
        loaded = config.load_config()
        assert loaded["quotaApi"]["apiKey"] == "glm_super_secret_key"
        assert loaded["quotas"][0]["apiKey"] == "ds_secret_key"
        assert loaded["quotas"][1]["apiKey"] == "zcode"

    def test_auto_migration_plain_to_dpapi(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "config.json"
        monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(config, "CONFIG_FILE", cfg_file)

        # 模拟旧版明文配置文件写入磁盘
        plain_data = {
            "quotaApi": {
                "apiKey": "old_plaintext_key_to_migrate"
            },
            "quotas": [
                {"name": "Kimi", "provider": "kimi", "apiKey": "kimi_plain_key"}
            ]
        }
        cfg_file.write_text(json.dumps(plain_data), encoding="utf-8")

        # 首次 load_config 读取旧明文并触发静默迁移
        loaded = config.load_config()
        assert loaded["quotaApi"]["apiKey"] == "old_plaintext_key_to_migrate"
        assert loaded["quotas"][0]["apiKey"] == "kimi_plain_key"

        # 验证磁盘上的明文已经被自动迁移为密文
        disk_data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert disk_data["quotaApi"]["apiKey"].startswith("dpapi:")
        assert disk_data["quotas"][0]["apiKey"].startswith("dpapi:")


class TestSourcesConfig:
    def test_default_sources(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        cfg = config.load_config()
        assert "sources" in cfg
        assert cfg["sources"]["quota"]["enabled"] is True
        assert cfg["sources"]["quota"]["intervalSec"] == 600

    def test_sources_merged(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"sources": {"system": {"enabled": True, "intervalSec": 2}}}),
            encoding="utf-8",
        )
        cfg = config.load_config()
        assert cfg["sources"]["system"]["enabled"] is True
        assert cfg["sources"]["system"]["intervalSec"] == 2
        assert cfg["sources"]["quota"]["enabled"] is True


class TestPanelCardsConfig:
    def test_default_panel_cards(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        cfg = config.load_config()
        assert "panelCards" in cfg
        cards = cfg["panelCards"]
        assert isinstance(cards, list)
        card_ids = [c["id"] for c in cards]
        assert card_ids == ["schedule", "todos", "system", "quotas", "weather", "dev"]
        assert all(c["enabled"] is True for c in cards)

    def test_custom_order_and_enabled_preserved(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        custom_cards = [
            {"id": "system", "enabled": True},
            {"id": "todos", "enabled": False},
            {"id": "quotas", "enabled": True},
            {"id": "schedule", "enabled": False},
        ]
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"panelCards": custom_cards}),
            encoding="utf-8",
        )
        cfg = config.load_config()
        cards = cfg["panelCards"]
        card_ids = [c["id"] for c in cards]
        # 前4个按照自定义顺序排布，且未包含的 weather 和 music 自动补齐在末尾
        assert card_ids == ["system", "todos", "quotas", "schedule", "weather", "dev"]
        assert cards[0]["enabled"] is True
        assert cards[1]["enabled"] is False
        assert cards[2]["enabled"] is True
        assert cards[3]["enabled"] is False
        assert cards[4]["enabled"] is True
        assert cards[5]["enabled"] is True

    def test_legacy_alias_migration(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        legacy_cards = [
            {"id": "tiles", "enabled": False},
            {"id": "header", "enabled": True},
        ]
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"panelCards": legacy_cards}),
            encoding="utf-8",
        )
        cfg = config.load_config()
        cards = cfg["panelCards"]
        card_ids = [c["id"] for c in cards]
        # tiles 转换为 quotas，header 转换为 schedule
        assert card_ids[0] == "quotas"
        assert cards[0]["enabled"] is False
        assert card_ids[1] == "schedule"
        assert cards[1]["enabled"] is True
        # 补齐其它卡片
        assert set(card_ids) == {"schedule", "todos", "system", "quotas", "weather", "dev"}

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        cfg = config.load_config()
        cfg["panelCards"] = [
            {"id": "todos", "name": "待办事项", "enabled": True},
            {"id": "system", "name": "电脑状态监控", "enabled": False},
        ]
        config.save_config(cfg)
        loaded = config.load_config()
        assert loaded["panelCards"][0]["id"] == "todos"
        assert loaded["panelCards"][0]["enabled"] is True
        assert loaded["panelCards"][1]["id"] == "system"
        assert loaded["panelCards"][1]["enabled"] is False
        # 补齐后其余卡片存在
        assert len(loaded["panelCards"]) == 6


class TestDisplayMode:
    def test_default_display_mode(self):
        cfg = config.load_config()
        assert cfg["style"].get("displayMode") in ("full", "capsule")

    def test_display_mode_validation(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"style": {"displayMode": "invalid_mode"}}),
            encoding="utf-8",
        )
        cfg = config.load_config()
        assert cfg["style"]["displayMode"] == "full"

    def test_display_mode_capsule_persisted(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"style": {"displayMode": "capsule"}}),
            encoding="utf-8",
        )
        cfg = config.load_config()
        assert cfg["style"]["displayMode"] == "capsule"

    def test_capsule_slot_validation(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"style": {"capsuleLeft": "invalid", "capsuleRight": "quota"}}),
            encoding="utf-8",
        )
        cfg = config.load_config()
        assert cfg["style"]["capsuleLeft"] == "weather"
        assert cfg["style"]["capsuleRight"] == "quota"


class TestThemeModeConfig:
    def test_default_theme_mode_is_auto(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        cfg = config.load_config()
        assert cfg["style"]["themeMode"] == "auto"

    @pytest.mark.parametrize("mode", ["auto", "light", "dark"])
    def test_valid_theme_mode_persisted(self, tmp_path, monkeypatch, mode):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"style": {"themeMode": mode}}),
            encoding="utf-8",
        )
        cfg = config.load_config()
        assert cfg["style"]["themeMode"] == mode

    def test_invalid_theme_mode_falls_back_auto(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        tmp_path.joinpath("config.json").write_text(
            json.dumps({"style": {"themeMode": "neon"}}),
            encoding="utf-8",
        )
        cfg = config.load_config()
        assert cfg["style"]["themeMode"] == "auto"
