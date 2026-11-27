from unittest.mock import MagicMock
import pytest
from app.platform import autostart


class FakeRegKey:
    def __init__(self, data=None):
        self.data = data if data is not None else {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def test_app_name():
    assert autostart.APP_NAME == "AnyBar"
    assert "FocusBar" in autostart.LEGACY_APP_NAMES
    assert "TaskbarReminder" in autostart.LEGACY_APP_NAMES


def test_migrate_legacy_autostart(monkeypatch):
    reg_store = {"FocusBar": '"D:\\path\\FocusBar.exe"'}

    fake_key = FakeRegKey(reg_store)

    def fake_open_key(root, path, reserved, access):
        return fake_key

    def fake_query_val(key, name):
        if name not in key.data:
            raise FileNotFoundError(f"Key {name} not found")
        return key.data[name], 1

    def fake_set_val(key, name, reserved, type_, val):
        key.data[name] = val

    def fake_del_val(key, name):
        if name not in key.data:
            raise FileNotFoundError(f"Key {name} not found")
        del key.data[name]

    monkeypatch.setattr(autostart.winreg, "OpenKey", fake_open_key)
    monkeypatch.setattr(autostart.winreg, "QueryValueEx", fake_query_val)
    monkeypatch.setattr(autostart.winreg, "SetValueEx", fake_set_val)
    monkeypatch.setattr(autostart.winreg, "DeleteValue", fake_del_val)

    autostart.migrate_legacy_autostart()

    assert "AnyBar" in fake_key.data
    assert "FocusBar" not in fake_key.data
    assert fake_key.data["AnyBar"] == '"D:\\path\\FocusBar.exe"'


def test_is_enabled_with_anybar(monkeypatch):
    fake_key = FakeRegKey({"AnyBar": '"C:\\AnyBar.exe"'})
    monkeypatch.setattr(autostart.winreg, "OpenKey", lambda *args: fake_key)
    monkeypatch.setattr(autostart.winreg, "QueryValueEx", lambda k, name: (k.data[name], 1) if name in k.data else (_ for _ in ()).throw(FileNotFoundError))

    assert autostart.is_enabled() is True


def test_is_enabled_with_legacy(monkeypatch):
    fake_key = FakeRegKey({"FocusBar": '"C:\\FocusBar.exe"'})
    monkeypatch.setattr(autostart.winreg, "OpenKey", lambda *args: fake_key)
    monkeypatch.setattr(autostart.winreg, "QueryValueEx", lambda k, name: (k.data[name], 1) if name in k.data else (_ for _ in ()).throw(FileNotFoundError))

    assert autostart.is_enabled() is True


def test_is_enabled_false(monkeypatch):
    fake_key = FakeRegKey({})
    monkeypatch.setattr(autostart.winreg, "OpenKey", lambda *args: fake_key)
    monkeypatch.setattr(autostart.winreg, "QueryValueEx", lambda k, name: (k.data[name], 1) if name in k.data else (_ for _ in ()).throw(FileNotFoundError))

    assert autostart.is_enabled() is False


def test_enable_and_disable(monkeypatch):
    store = {}
    fake_key = FakeRegKey(store)

    monkeypatch.setattr(autostart.winreg, "CreateKey", lambda *args: fake_key)
    monkeypatch.setattr(autostart.winreg, "OpenKey", lambda *args: fake_key)
    monkeypatch.setattr(autostart.winreg, "SetValueEx", lambda k, name, r, t, val: k.data.__setitem__(name, val))
    monkeypatch.setattr(autostart.winreg, "DeleteValue", lambda k, name: k.data.pop(name, None))

    assert autostart.enable() is True
    assert "AnyBar" in store

    assert autostart.disable() is True
    assert "AnyBar" not in store
