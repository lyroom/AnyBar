import ctypes
from pathlib import Path
from app.platform import win32_utils


def test_native_uia_loaded():
    """验证原生 C++ 动态库存在且函数可成功加载与签名正确。"""
    dll_path = Path(__file__).resolve().parent.parent / "app" / "platform" / "taskbar_native.dll"
    assert dll_path.exists(), "taskbar_native.dll 必须存在于 app/platform/ 目录下"

    fn = win32_utils._NATIVE_UIA_FUNC
    assert fn is not None, "_load_native_uia 必须成功解析导出函数"

    # 验证安全调用（传非法参数时不崩溃且返回 0 或 int）
    val = fn(0, 0)
    assert isinstance(val, int)


def test_find_icon_right_edge_fallback(monkeypatch):
    """验证当原生 DLL 返回 0 或异常时，正确平滑回退。"""
    # 模拟原生 DLL 抛出异常
    monkeypatch.setattr(win32_utils, "_NATIVE_UIA_FUNC", lambda a, b: 1 / 0)

    # 模拟 subprocess 返回固定输出
    class DummyProc:
        stdout = "700.0 2500.0 500.0"

    monkeypatch.setattr(win32_utils.subprocess, "run", lambda *args, **kwargs: DummyProc())

    res = win32_utils.find_icon_right_edge_uia(2500, 500)
    assert res == 700
