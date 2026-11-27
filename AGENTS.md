# AGENTS.md — AnyBar（万能常驻条）

Windows 10/11 任务栏常驻提醒条：Python 3.13 + PySide6 (Qt 6) + ctypes Win32 互操作。**仅支持 Windows**（依赖 user32/dwmapi 与 `Shell_TrayWnd` 窗口结构），不要引入跨平台抽象或非 Windows 分支。

## 常用命令

```bash
# PATH 上的默认 python（miniconda base）没有 PySide6/pytest，须用项目环境：
PY=D:/Environment/conda_env/envs/touchbarcopy/python.exe

$PY main.py                      # 运行（首帧会做 UIA 图标边界探测/读缓存）
$PY -m pytest tests/ -q          # 单元测试（纯逻辑：config 调度计算 / logger，无 GUI 依赖）
$PY self_test.py                 # 嵌入自检，输出 EMBED: OK/FAIL（需真实桌面会话）
$PY -m PyInstaller build.spec --noconfirm   # 打包单 EXE → dist/AnyBar.exe
```

- `build.bat` 是给作者机器双击用的（硬编码上面这条 conda 路径），通用环境直接跑 pyinstaller 命令。
- 测试无独立配置文件；`tests/conftest.py` 把仓库根加入 sys.path，测试直接 `from app import ...`。改 `app/core/config.py` 后必须跑 pytest。

## 目录与架构（四层分层：Core / Platform / Styles / GUI）

- `main.py` — 入口：DPI 感知、单实例互斥体（`Local\AnyBarMutex`）、设置/退出信号绑定。
- `app/__init__.py` — 顶层包与用户插件兼容别名（将 `app.sources` / `app.tiles` 映射到 `app.core.sources` / `app.core.tiles` 同一模块单例）。
- `app/core/` — 纯业务逻辑与数据源层（禁止反向依赖 `app.gui`）：
  - `config.py` — 配置加载/保存/迁移 + 时段计算（current/next/schedule_progress）。**纯逻辑、不 import Qt**，加新配置项须同步改 `DEFAULT_CONFIG` 与 `load_config` 并补单测。
  - `logger.py` — 统一日志与 Qt 消息过滤。
  - `tiles.py` — Tile 统一数据协议（`make_tile`）。
  - `quota_api.py` — 多平台算力余额查询（GLM 个人/团队 `?type=2` + `Bigmodel-Organization/Bigmodel-Project`、`~/.zcode/v2/credentials.json` 自动发现、Codex/Claude/Cursor/DeepSeek/Magpie 等；纯解析函数可单测）。
  - `source_service.py` — 后台数据源轮询调度器（守护线程 + Qt Signal）。
  - `sources/` — 可插拔数据源注册表（`@register` 装饰器 + 内置 system/weather/dev/quota/claude/cursor/deepseek 源 + 用户本地 `%APPDATA%/AnyBar/plugins/*.py` 热加载）。
- `app/platform/` — Windows 平台底层互操作层（禁止反向依赖 `app.gui`）：
  - `win32_utils.py` — 任务栏查找、DPI、全屏检测、原生 C++ DLL (`taskbar_native.dll`) 与 PowerShell 兜底 UIA 扫描、WinEvent 钩子。ctypes 函数**必须显式声明 argtypes/restype**（HDC 等 64 位句柄不声明会 `OverflowError`）。
  - `glass.py` — 窗口背景材质与深浅色标题栏同步。
  - `autostart.py` — 注册表 Run 键开机自启。
  - `native/taskbar_uia.cpp` + `taskbar_native.dll` — 原生 UIA 探测库。
- `app/styles/` — 设计令牌与独立 QSS 引擎（禁止反向依赖 `app.gui`）：
  - `tokens.py` — 深浅色语义色板、圆角/间距/动效令牌与 `spx()` DPI 换算。
  - `qss_engine.py` — 外部 `.qss` 模板加载、`{{token}}` / `{{px:N}}` 编译缓存与动态属性辅助（`set_role` / `set_prop` / `repolish`）。
  - `theme.py` — 全局主题模式（auto/light/dark）、字体与样式表入口。
  - `icons.py` / `weather_glyph.py` — 矢量图标库与动态天气自绘。
  - `qss/` — 独立样式表（`common.qss`、`menu.qss`、`hover_panel.qss`、`settings.qss`、`dialogs.qss`、`buttons_inputs.qss`），**禁止在 GUI 子组件中散落静态内联 `setStyleSheet`**。
- `app/gui/` — 表现层（按窗口职责与设计模式拆分）：
  - `widgets/` — 共享通用控件库：`motion.py`（动效/Toast/平滑切页）、`surfaces.py`（`SurfaceCard`、`SettingGroupCard`）、`controls.py`（`ToggleSwitch`、`SlidingSegmentedControl`、图标按钮）、`indicators.py`（进度条/圆环/状态点）、`reorder.py`（拖拽排序容器）、`scroll_label.py`。
  - `taskbar/` — 任务栏常驻应用：`window.py`（嵌入/定位/避让/全屏隐藏/悬停联动，500ms 兜底 + WinEvent 0.2s 节流）、`widget.py`（主自绘控件 + 跑马灯 + 每帧 `SWP_FRAMECHANGED`）、`menu_builder.py`（右键菜单 Builder）、`views/`（Strategy + Registry 视图策略：`schedule_view` / `tiles_view` / `weather_view` / `capsule_view`）。
  - `hover_panel/` — 悬停浮窗：`panel.py`（主壳层与原位增量刷新）、`primitives.py`（卡片原语）、`registry.py`（`PanelCardRegistry`）、`cards/`（Composite Card 模式拆分的 7 大独立卡片：schedule / todo / weather / system / quota / dev / music）。
  - `settings/` — 设置中心：`dialog.py`（Mediator 壳层）、`form_helpers.py`、`quota_controller.py`、`coding_plan_dialog.py`（算力向导弹窗）、`pages/`（Page Presenter 模式拆分的 6 大标签页：schedule / todo / bar_style / appearance / extensions / plugins）。
- `data/config.json` — 用户本地配置（已 gitignore，仓库仅跟踪脱敏模板 `data/config.example.json`）；`data/uia_cache.json` — 运行时缓存（已 gitignore，勿提交）。
- `需求和当前技术栈.md` — **改任何嵌入/定位/绘制相关代码前必读**，尤其 §4「关键技术决策与勿重试清单」。

## 核心规则（违反会复现已修复的 bug）

- 嵌入采用 v3 方案：本进程内创建 `AnyBarHostWnd` 中转窗口再 `SetParent` 挂入 `Shell_TrayWnd`。跨进程 SetParent 会被系统静默拒绝；不要回退 TOPMOST 悬浮窗方案。
- 勿重试清单（实测无效/有害，完整版见设计文档 §4.2）：`SetLayeredWindowAttributes(LWA_ALPHA)`；acrylic 毛玻璃（hit-test 全面穿透）；在子 widget 上调 `self.winId()`（必须用 `self.window().winId()`）；用 `update()`/`RedrawWindow`/`DwmFlush` 修滚动冻结（唯一解是每帧 `SWP_FRAMECHANGED`）；嵌入窗口上用 `mapToGlobal`（右键菜单须用 `QCursor.pos()`）；嵌入窗口内 `hide()+show()`（winId 变化导致嵌入丢失）；`ctypes.windll.kernel32.GetLastError()`（必须 `WinDLL(use_last_error=True)` + `ctypes.get_last_error()`）；GetPixel 扫描图标边界（自反馈横跳）。
- glass 常态背景 alpha 必须 ≥ 28；alpha=1 时空白处鼠标穿透到任务栏。
- cfg 引用唯一性：更新配置必须 `cfg.clear()` + `cfg.update(new)` 原地改，禁止 `self._cfg = new_dict`（悬停面板与条共享同一 dict 引用，换引用会状态失同步）。
- 设置对话框「应用后取消」：`_on_apply` 落盘后必须 `self._snapshot = deepcopy(self._cfg)`，否则取消回滚内存但磁盘已是新值。
- PowerShell 子进程必须带 `CREATE_NO_WINDOW`（windowed exe 否则闪黑框）。
- QSS 纯声明式与选择器语法不可混用在同一个 `setStyleSheet`（解析失败整段失效）。
- 缩放：入口设 `QT_ENABLE_HIGHDPI_SCALING=0`，物理像素 = 逻辑值 × `theme.screen_scale()`；改布局尺寸时一律走该换算，勿假设 96 DPI。
- 全屏检测有多组白名单（`_SHELL_HOST_PROCS`、`WS_EX_TOOLWINDOW` 排除），改动前先读设计文档 §4.7「全屏误判四连坑」。
- 短命 QObject（右键 `QMenu`、面板 `QPropertyAnimation` 等）以常驻控件为 parent 创建后，替换/用完必须 `deleteLater()`：只丢引用不删会随右键/悬停次数无限累积为子对象（实测复现，复核脚本 `_tmp_leak_verify.py`）。
- 悬浮窗卡片生命周期规范：在悬浮窗上增加任何新卡片，必须在 `DEFAULT_PANEL_CARDS` 中注册、`app/gui/hover_panel/cards/` 中实现并注册进 `PanelCardRegistry`，且在设置「界面与浮窗」页的任务栏悬浮窗卡片定制与排序列表中加入对应项，支持修改排列与显隐开关；严禁在 `app/gui/hover_panel/panel.py` 中绕过 `panelCards` 强行兜底追加渲染，所有卡片必须 100% 遵循用户配置的排序与勾选状态。

## 日志

用 `app.core.logger.get_logger(name, filename, env_var=...)`，勿直接 `logging.getLogger`。默认写 `%TEMP%\anybar\`，RotatingFileHandler 1MB×1。环境变量：`TOUCHBAR_LOG_DIR`（目录）、`TOUCHBAR_LOG_LEVEL`（级别）；每个 logger 可传 env_var 指定专属文件（现有 reposition.log / tick.log）。Qt 消息经 `install_qt_message_filter` 过滤良性告警。

## 约定

- 注释、docstring、用户可见文案、文档均为中文；标识符英文。
- 无 lint/format 配置，风格跟随现有文件（4 空格缩进、双引号）。
- 临时验证/诊断脚本（`_tmp_*.py`、`_diag_*.py` 等）不要提交；`.gitignore` 已列出部分模式。
- 打包：`build.spec` 从 conda 的 `Library\bin` 收集 ffi/liblzma/libbz2/libmpdec DLL，并打包 `app/platform/taskbar_native.dll` 与 `app/styles/qss`，排除 tkinter/unittest 等；配置读写已按 `sys.frozen` 适配 exe 同级 `data/` 目录。
