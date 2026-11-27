"""app/gui/settings/quota_controller.py — 算力套餐凭据自动探测与异步连通性测试控制器"""

from __future__ import annotations

import os
import threading
from typing import Any

from PySide6.QtCore import QObject, Signal

from app.core import quota_api


def discover_local_quota_candidates() -> list[dict[str, Any]]:
    """探测本机已登录/环境变量中配置的 AI 算力平台凭据与 Magpie 渠道（无 UI 依赖）。"""
    from app.core.sources.claude_source import discover_claude_auth
    from app.core.sources.cursor_source import discover_cursor_session

    found: list[dict[str, Any]] = []

    try:
        codex_auth = quota_api.discover_codex_auth()
        if codex_auth:
            found.append({
                "provider": "codex",
                "name": "Codex",
                "apiKey": "",
                "label": f"ChatGPT Codex ({codex_auth.get('plan', 'Plus')})",
            })
    except Exception:
        pass

    try:
        claude_auth = discover_claude_auth()
        if claude_auth:
            found.append({
                "provider": "claude",
                "name": "Claude",
                "apiKey": claude_auth.get("apiKey", ""),
                "label": "Claude",
            })
    except Exception:
        pass

    try:
        cursor_tok = discover_cursor_session()
        if cursor_tok:
            found.append({
                "provider": "cursor",
                "name": "Cursor",
                "apiKey": cursor_tok,
                "label": "Cursor",
            })
    except Exception:
        pass

    try:
        ds_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if ds_key:
            found.append({
                "provider": "deepseek",
                "name": "DeepSeek",
                "apiKey": ds_key,
                "label": "DeepSeek",
            })
    except Exception:
        pass

    try:
        cards = quota_api.fetch_magpie_quotas("http://127.0.0.1:3425")
        if isinstance(cards, dict):
            cards = cards.get("cards") or []
        for c in cards[:4]:
            prov_key = str(c.get("provider") or "").strip()
            title = str(c.get("title") or c.get("name") or prov_key)
            item: dict[str, Any] = {
                "provider": "magpie",
                "name": title,
                "apiKey": prov_key,
                "label": title,
            }
            w = quota_api.primary_window(c.get("windows"))
            if w and w.get("percent") is not None:
                item["used"] = round(float(w["percent"]), 1)
                item["limit"] = 100
                item["unit"] = "%"
            elif c.get("balance"):
                item["balance"] = str(c.get("balance"))
            found.append(item)
    except Exception:
        pass

    return found


class QuotaSyncController(QObject):
    """负责在守护线程中批量执行算力渠道连通性测试，通过 Qt Signal 安全回投主线程。"""

    rows_updated = Signal(object)
    sync_finished = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._busy = False

    @property
    def is_busy(self) -> bool:
        return self._busy

    def start_sync(self, row_tasks: list[tuple[int, dict[str, Any]]]) -> bool:
        if self._busy or not row_tasks:
            return False
        self._busy = True

        def _work():
            updates = []
            summaries = []
            errors = []
            for idx, item in row_tasks:
                try:
                    res = quota_api.fetch_provider_quota(item)
                    updates.append((idx, res))
                    r_name = res.get("name") or item["name"]
                    if res.get("used") is not None and res.get("limit") is not None:
                        if res.get("unit") == "%" and res.get("limit") == 100:
                            summaries.append(f"{r_name} 剩余 {int(round(float(res['used'])))}%")
                        else:
                            summaries.append(f"{r_name} 剩余 {res['used']}/{res['limit']}")
                    elif res.get("balance"):
                        summaries.append(f"{r_name} {res['balance']}")
                    else:
                        summaries.append(str(r_name))
                except Exception as exc:
                    errors.append(f"{item['name']}: {exc}")
            self.rows_updated.emit(updates)
            if summaries:
                txt = f"✓ 实时同步成功 · {' | '.join(summaries[:4])}"
                if errors:
                    txt += f" （{len(errors)} 项失败）"
            else:
                txt = f"✗ {'; '.join(errors[:2])}"
            self._busy = False
            self.sync_finished.emit(txt)

        threading.Thread(target=_work, daemon=True).start()
        return True
