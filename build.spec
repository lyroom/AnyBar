# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

# conda 环境的 Library\bin 下部分 DLL 不在 PyInstaller 默认搜索路径，
# 显式收集 _ctypes/_lzma/_bz2/_decimal/_ssl 所需的运行时 DLL，避免打包后 import 失败或被 PATH 上的旧 DLL 覆盖。
_CONDA_BIN = Path(sys.executable).resolve().parent / "Library" / "bin"
_EXTRA_DLLS = []
for _name in ("ffi.dll", "liblzma.dll", "libbz2.dll", "libmpdec-4.dll", "libcrypto-3-x64.dll", "libssl-3-x64.dll"):
    _p = _CONDA_BIN / _name
    if _p.exists():
        _EXTRA_DLLS.append((str(_p), "."))

# 收集项目自研的微型原生 UIA C++ 动态库（taskbar_native.dll）
_native_dll = Path("app/platform/taskbar_native.dll").resolve()
if _native_dll.exists():
    _EXTRA_DLLS.append((str(_native_dll), "."))

# 收集 Qt 简体中文翻译包与独立 QSS 样式表模板，确保打包单 EXE 后样式与汉化完整
_EXTRA_DATAS = [("assets", "assets"), ("app/styles/qss", "app/styles/qss")]
try:
    from PySide6.QtCore import QLibraryInfo
    _qt_zh = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)) / "qtbase_zh_CN.qm"
    if _qt_zh.exists():
        _EXTRA_DATAS.append((str(_qt_zh), "translations"))
except Exception:
    pass

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=_EXTRA_DLLS,
    datas=_EXTRA_DATAS,
    hiddenimports=["PySide6.QtSvg", "ssl", "_ssl"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Python 标准库冗余
        "tkinter",
        "unittest",
        "pydoc",
        "doctest",
        "test",
        "sqlite3",
        "lib2to3",
        # PySide6 未使用子模块排除（大幅精简体积）
        "PySide6.QtNetwork",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtXml",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtPrintSupport",
        "PySide6.QtDesigner",
        "PySide6.QtBluetooth",
        "PySide6.QtDBus",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtPositioning",
        "PySide6.QtWebChannel",
        "PySide6.QtWebSockets",
        "PySide6.QtNfc",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtSpatialAudio",
        "PySide6.QtStateMachine",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AnyBar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)
