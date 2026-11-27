"""app/sources/dev_source.py — 轻量 DevOps / Git 分支与改动监控微胶囊

本地高频极速数据源：
1. 自动检测当前工作区（或用户指定本地仓库）的 Git 分支名称与未提交改动状态；
2. 纯 Python 0 依赖极速解析 .git/HEAD 与轻量 status；
3. 产出标称微胶囊 Tile: git:branch（例如 🌿 master (+3)）；
4. 提供一键通过 Windows Terminal / PowerShell 唤起终端打开当前仓库能力。
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from app.core.tiles import make_tile

from . import SourceInfo, register

# Windows 进程静默标志（CREATE_NO_WINDOW）
CREATE_NO_WINDOW = 0x08000000


def find_git_root(start_path: Path | str | None = None) -> Path | None:
    """从起始路径开始递归向上查找包含 .git 的仓库根目录。"""
    if start_path is None:
        p = Path.cwd().resolve()
    else:
        p = Path(start_path).resolve()

    # 针对指向具体文件的情况
    if p.is_file():
        p = p.parent

    for cur in [p] + list(p.parents):
        git_dir = cur / ".git"
        if git_dir.exists():
            return cur
    return None


def read_git_head_branch(git_root: Path) -> str:
    """纯 Python 高速读取 .git/HEAD 分支名（耗时 < 1ms，无子进程开销）。"""
    git_marker = git_root / ".git"
    real_git_dir = git_marker

    # 支持 git worktree 或 submodule 中的 gitdir: 指针
    if git_marker.is_file():
        try:
            content = git_marker.read_text(encoding="utf-8").strip()
            if content.startswith("gitdir:"):
                target = content[7:].strip()
                real_git_dir = (git_root / target).resolve()
        except OSError:
            pass

    head_file = real_git_dir / "HEAD"
    if not head_file.exists():
        return "unknown"

    try:
        head_content = head_file.read_text(encoding="utf-8", errors="ignore").strip()
        if head_content.startswith("ref: refs/heads/"):
            return head_content[len("ref: refs/heads/"):].strip()
        if head_content.startswith("ref:"):
            return head_content.split("/")[-1].strip()
        # detached HEAD: 显示前 7 位 commit hash
        if len(head_content) >= 7:
            return head_content[:7]
        return head_content
    except OSError:
        return "unknown"


def get_git_dirty_count(git_root: Path, timeout: float = 1.5) -> int:
    """获取工作区未提交的文件变更数量（staged + unstaged + untracked）。

    使用轻量 git status --porcelain=v1 并强制带 CREATE_NO_WINDOW，
    若环境无 git 或超时则优雅降级为 0。
    """
    if not shutil.which("git"):
        return 0

    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain=v1", "-uall"],
            cwd=str(git_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        if proc.returncode == 0:
            lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
            return len(lines)
    except (subprocess.SubprocessError, OSError):
        pass
    return 0


def open_repo_terminal(repo_path: str | Path) -> bool:
    """通过系统默认现代终端（优先 Windows Terminal，次选 PowerShell）打开仓库目录。"""
    p = Path(repo_path).resolve()
    if not p.exists():
        return False

    repo_str = str(p)
    # 1. 优先尝试 Windows Terminal (wt.exe)
    if shutil.which("wt"):
        try:
            subprocess.Popen(
                ["wt.exe", "-d", repo_str],
                creationflags=subprocess.DETACHED_PROCESS,
            )
            return True
        except OSError:
            pass

    # 2. 次选 PowerShell
    try:
        cmd = f"Set-Location -LiteralPath '{repo_str}'"
        subprocess.Popen(
            ["powershell.exe", "-NoExit", "-Command", cmd],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return True
    except OSError:
        pass

    # 3. 兜底系统 explorer
    try:
        os.startfile(repo_str)
        return True
    except OSError:
        return False


@register(
    SourceInfo(
        id="dev",
        title="DevOps / Git 状态看板",
        description="实时监控本地 Git 仓库分支名与未提交文件数，点击一键唤起系统终端",
        kind="local",
        default_interval_sec=5,
        min_interval_sec=1,
        needs_credentials=False,
    )
)
def fetch_dev_tiles(cfg: dict[str, Any], timeout: float = 2.0) -> list[dict[str, Any]]:
    """作为通用 Source 时的抓取入口，输出轻量 Git 分支微胶囊 Tile。"""
    src_cfg = (cfg.get("sources") or {}).get("dev") or {}
    custom_path = str(src_cfg.get("repoPath") or "").strip()

    target_path = None
    if custom_path and Path(custom_path).exists():
        target_path = Path(custom_path)
    else:
        env_path = os.environ.get("ANYBAR_DEV_REPO", "").strip()
        if env_path and Path(env_path).exists():
            target_path = Path(env_path)

    git_root = find_git_root(target_path)
    if not git_root:
        # 未处于 Git 仓库目录时输出待机占位微胶囊
        return [
            make_tile(
                id="git:branch",
                source="dev",
                name="Git",
                ratio=1.0,
                center_text="Git",
                sub_text="🌿 待机 (未检测到仓库)",
                color="#6B7280",
                kind="text",
                status="ok",
                repo_path="",
                branch="",
                dirty_count=0,
            )
        ]

    branch = read_git_head_branch(git_root)
    dirty_count = get_git_dirty_count(git_root, timeout=timeout)

    # 状态美化：clean 时显示洁净绿，有改动时根据数量过渡
    if dirty_count == 0:
        sub_text = f"🌿 {branch} (clean)"
        ratio = 1.0
        color = "#10B981"  # Emerald 绿
    else:
        sub_text = f"🌿 {branch} (+{dirty_count})"
        ratio = max(0.2, min(1.0, 1.0 - dirty_count * 0.08))
        color = "#F59E0B" if dirty_count < 10 else "#EF4444"

    # center_text 精炼展示：主分支简写或截断
    center_text = branch if len(branch) <= 12 else branch[:10] + "…"

    return [
        make_tile(
            id="git:branch",
            source="dev",
            name="Git",
            ratio=ratio,
            center_text=center_text,
            sub_text=sub_text,
            color=color,
            kind="text",
            status="ok",
            repo_path=str(git_root),
            branch=branch,
            dirty_count=dirty_count,
        )
    ]
