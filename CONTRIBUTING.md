# AnyBar 贡献者指南 (Contributing Guide)

欢迎参与 AnyBar 的开源建设！AnyBar 采用**数据源插件化架构**，你可以非常轻松地为 AnyBar 增加各种实时信息展示：例如**股票行情**、**电脑硬件监控**、**网易云歌词**、**日历提醒**等。

得益于插件化设计，**新增一个数据源仅需编写 1 个 Python 模块并使用 `@register` 登记，无需修改任何核心绘制与界面代码**。

---

## 快速上手：如何编写一个新的数据源

所有内置数据源文件均存放在 [`app/core/sources/`](file:///app/core/sources/) 目录下（用户外部插件 `%APPDATA%/AnyBar/plugins/*.py` 可继续使用兼容别名 `from app.sources import ...` 与 `from app.tiles import make_tile`）。

### 步骤 1：新建源文件 `app/core/sources/xxx_source.py`

以编写一个「股票行情数据源」为例：

```python
"""app/core/sources/stock_source.py — 股票行情数据源"""
from __future__ import annotations
import time
from typing import Any
from app.core.tiles import make_tile
from . import SourceInfo, register


@register(
    SourceInfo(
        id="stock",                           # 数据源唯一标识
        title="股票行情监控",                  # 设置页展示名称
        kind="remote",                        # "local"(本地无网络) | "remote"(远程网络 IO)
        default_interval_sec=30,              # 默认刷新周期（秒）
        min_interval_sec=5,                   # 允许用户配置的最小周期
        needs_credentials=True,               # 是否需要配置 Key/Token
    )
)
def fetch_stock_tiles(cfg: dict[str, Any], timeout: float = 6.0) -> list[dict[str, Any]]:
    """拉取股票数据并返回标准 Tile 列表。"""
    # 1. 从配置中读取凭据或关注的代码列表
    stock_cfg = (cfg.get("sources") or {}).get("stock") or {}
    symbols = stock_cfg.get("symbols", ["600519", "AAPL"])

    # 2. 发起查询（纯 Python 逻辑，带超时控制）
    # quotes = fetch_quotes_from_api(symbols, timeout=timeout)
    # 模拟数据：
    quotes = [
        {"symbol": "茅台", "price": "1780", "pct": 2.3},
        {"symbol": "苹果", "price": "$220", "pct": -0.8},
    ]

    # 3. 构造并返回标准 Tile 列表
    tiles = []
    for q in quotes:
        pct = float(q["pct"])
        color = "#EF4444" if pct >= 0 else "#10B981"  # A股红涨绿跌
        tile = make_tile(
            id=f"stock:{q['symbol']}",
            source="stock",
            name=q["symbol"],
            ratio=abs(pct) / 10.0,             # 涨跌幅映射为圆环进度
            center_text=f"{pct:+.1f}%",        # 圆环中心大字
            sub_text=q["price"],               # 第二行说明
            color=color,                       # 语义颜色
            kind="ring",                       # "ring"(圆环指标) 或 "text"(走马灯文本流)
        )
        tiles.append(tile)
    return tiles
```

### 步骤 2：在 `app/core/sources/__init__.py` 中引入模块

在 [`app/core/sources/__init__.py`](file:///app/core/sources/__init__.py) 的 `_load_builtin_sources` 中添加一行导入：

```python
def _load_builtin_sources() -> None:
    from . import quota_source, system_source, stock_source  # noqa: F401
```

**就此完成！**
- 任务栏常驻条 (BarWidget) 自动支持显示该数据源的圆环或文字；
- 悬停浮窗面板 (HoverPanel) 自动渲染该数据源卡片；
- 设置界面 (SettingsDialog) 自动生成该数据源的启用开关与轮询间隔配置。

---

## Tile 统一数据协议规范

每个数据源返回的项均为标准的 `Tile` 字典，推荐使用 `app.tiles.make_tile()` 构造：

| 字段 | 类型 | 说明 | 示例 |
| :--- | :--- | :--- | :--- |
| `id` | `str` | 全局唯一 ID | `"stock:600519"`、`"system:cpu"` |
| `source` | `str` | 所属源 ID | `"stock"`、`"system"`、`"quota"` |
| `name` | `str` | 条上及面板卡片显示标题 | `"茅台"`、`"CPU"`、`"GLM-4"` |
| `kind` | `str` | 呈现范式：`"ring"` 或 `"text"` | 数值监控用 `"ring"`，歌词/日程用 `"text"` |
| `ratio` | `float \| None` | 0.0 ~ 1.0 的百分比进度环 | `0.45`（代表 45% 使用率） |
| `center_text`| `str` | 圆环中心醒目大字 | `"45%"`、`"+2.3%"`、`"¥"` |
| `sub_text` | `str` | 第二行辅助说明文字 | `"16核"`、`"1780"`、`"8.5/20"` |
| `color` | `str` | 语义颜色（Hex 格式），缺省按 ratio 阶梯给 | `"#34C759"`、`"#FF3B30"` |
| `status` | `str` | 状态：`"ok"`、`"warn"`、`"err"` | `"ok"` |

---

## 开发与测试准则

1. **环境准备**：
   ```bash
   # 激活你的 Python 3.13+ 虚拟环境并安装开发依赖
   pip install -r requirements.txt pytest
   ```
2. **纯逻辑单元测试**：
   数据源及业务逻辑必须保持纯粹，禁止直接依赖 Qt GUI。编写完成后执行测试：
   ```bash
   python -m pytest tests/ -q
   ```
3. **离屏冒烟测试（防内存泄漏）**：
   在提交 PR 前，必须运行冒烟检查脚本：
   ```bash
   python scripts/smoke.py
   ```
   确保输出 `VERIFY: OK (冒烟与防泄漏检查全部通过)`。
4. **Win32 底层红线**：
   请在改动任何底层窗口相关代码前必读 [`AGENTS.md`](file:///AGENTS.md) 与 [`需求和当前技术栈.md`](file:///需求和当前技术栈.md) 中的「勿重试清单」。
