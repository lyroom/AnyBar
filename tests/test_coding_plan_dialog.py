import copy
import pytest
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import Qt

from app.gui.settings import CodingPlanDialog, SettingsDialog
from app.core import config as config_mod


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_coding_plan_dialog_init_empty(qapp):
    dlg = CodingPlanDialog(None, item_data=None, dark=True, scale=1.0)
    assert dlg is not None
    data = dlg.get_data()
    assert "provider" in data
    assert "name" in data
    dlg.deleteLater()


def test_coding_plan_dialog_init_with_data(qapp):
    init_data = {
        "name": "我的 DeepSeek",
        "provider": "deepseek",
        "apiKey": "sk-test-12345",
        "value": "88.50",
        "limit": "100",
        "unit": "CNY",
    }
    dlg = CodingPlanDialog(None, item_data=init_data, dark=False, scale=1.0)
    data = dlg.get_data()
    assert data["name"] == "我的 DeepSeek"
    assert data["provider"] == "deepseek"
    assert data["apiKey"] == "sk-test-12345"
    assert data["value"] == "88.50"
    assert data["unit"] == "CNY"
    dlg.deleteLater()


def test_coding_plan_dialog_provider_switching(qapp):
    dlg = CodingPlanDialog(None, item_data=None, dark=True, scale=1.0)

    # 切换至 Cursor
    idx_cur = dlg._prov_combo.findData("cursor")
    assert idx_cur >= 0
    dlg._prov_combo.setCurrentIndex(idx_cur)
    assert dlg._param_stack.currentIndex() == 0
    assert "Cursor" in dlg._name_edit.text()

    # 切换至 GLM
    idx_glm = dlg._prov_combo.findData("glm")
    dlg._prov_combo.setCurrentIndex(idx_glm)
    assert dlg._param_stack.currentIndex() == 1
    assert "GLM" in dlg._name_edit.text()

    # 切换至 Magpie
    idx_mp = dlg._prov_combo.findData("magpie")
    dlg._prov_combo.setCurrentIndex(idx_mp)
    assert dlg._param_stack.currentIndex() == 2

    # 切换至 Manual
    idx_man = dlg._prov_combo.findData("manual")
    dlg._prov_combo.setCurrentIndex(idx_man)
    assert dlg._param_stack.currentIndex() == 3

    dlg.deleteLater()


def test_coding_plan_dialog_test_connection_mock(qapp, monkeypatch):
    dlg = CodingPlanDialog(None, item_data=None, dark=True, scale=1.0)
    dlg._name_edit.setText("测试 DeepSeek")
    idx = dlg._prov_combo.findData("deepseek")
    dlg._prov_combo.setCurrentIndex(idx)
    dlg._api_key_edit.setText("sk-fake-key")

    fake_res = {
        "provider": "deepseek",
        "balance": "99.80",
        "unit": "CNY",
        "status": "ok",
    }
    monkeypatch.setattr("app.gui.settings.coding_plan_dialog.fetch_provider_quota", lambda item, timeout=8.0: fake_res)

    # 触发连接测试
    dlg._on_test_connection()

    # 等待异步结果回调
    import time
    t0 = time.time()
    while time.time() - t0 < 1.0 and not dlg._test_result_data:
        QApplication.processEvents()
        time.sleep(0.02)

    assert dlg._test_result_data.get("balance") == "99.80"
    data = dlg.get_data()
    assert data["balance"] == "99.80"
    dlg.deleteLater()


def test_settings_dialog_add_quota_row_integration(qapp, monkeypatch):
    cfg = copy.deepcopy(config_mod.DEFAULT_CONFIG)
    cfg["quotas"] = []
    dlg = SettingsDialog(None, cfg)

    # 拦截 CodingPlanDialog.exec 返回 Accepted 并提供 mock 数据
    mock_data = {
        "name": "集成测试套餐",
        "provider": "cursor",
        "apiKey": "test-session-token",
        "used": 120.0,
        "limit": 500.0,
        "unit": "req",
    }
    monkeypatch.setattr(CodingPlanDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(CodingPlanDialog, "get_data", lambda self: mock_data)

    # 触发添加算力套餐
    dlg._on_click_add_quota()

    assert len(dlg._quota_rows) == 1
    row = dlg._quota_rows[0]
    assert row["name"].text() == "集成测试套餐"
    assert str(row["provider"].currentData()) == "cursor"
    assert row["apiKey"].text() == "test-session-token"
    assert row["value"].text() == "120" or row["value"].text() == "120.0"
    assert row["limit"].text() == "500" or row["limit"].text() == "500.0"

    # 测试修改编辑当前行
    edit_data = {
        "name": "已修改的套餐",
        "provider": "deepseek",
        "apiKey": "sk-updated",
        "used": 50.0,
        "limit": 100.0,
        "unit": "CNY",
    }
    monkeypatch.setattr(CodingPlanDialog, "get_data", lambda self: edit_data)
    dlg._on_edit_quota_row(row)

    assert row["name"].text() == "已修改的套餐"
    assert str(row["provider"].currentData()) == "deepseek"
    assert row["apiKey"].text() == "sk-updated"

    # 验证 collect_config 落盘数据结构
    dlg._collect_config()
    saved_quotas = dlg._cfg["quotas"]
    assert len(saved_quotas) == 1
    assert saved_quotas[0]["name"] == "已修改的套餐"
    assert saved_quotas[0]["provider"] == "deepseek"
    assert saved_quotas[0]["apiKey"] == "sk-updated"

    dlg.deleteLater()
