"""tests/test_dev_source.py — DevOps / Git 状态微胶囊数据源单元测试。"""

from pathlib import Path
import pytest

from app.core.sources import dev_source, get_source


def test_dev_source_registration():
    reg = get_source("dev")
    assert reg is not None
    assert reg.info.id == "dev"
    assert reg.info.kind == "local"
    assert reg.info.default_interval_sec == 5
    assert reg.info.needs_credentials is False


def test_find_git_root(tmp_path):
    repo_dir = tmp_path / "my_project"
    sub_dir = repo_dir / "src" / "deep" / "pkg"
    sub_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / ".git").mkdir(parents=True, exist_ok=True)

    found = dev_source.find_git_root(sub_dir)
    assert found == repo_dir.resolve()

    not_repo = tmp_path / "other"
    not_repo.mkdir()
    assert dev_source.find_git_root(not_repo) is None


def test_read_git_head_branch_ref(tmp_path):
    repo_dir = tmp_path / "repo"
    git_dir = repo_dir / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    head_file = git_dir / "HEAD"
    head_file.write_text("ref: refs/heads/feature/phase-2-ai\n", encoding="utf-8")

    branch = dev_source.read_git_head_branch(repo_dir)
    assert branch == "feature/phase-2-ai"


def test_read_git_head_branch_detached(tmp_path):
    repo_dir = tmp_path / "repo"
    git_dir = repo_dir / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    head_file = git_dir / "HEAD"
    head_file.write_text("a1b2c3d4e5f6789012345678901234567890abcd\n", encoding="utf-8")

    branch = dev_source.read_git_head_branch(repo_dir)
    assert branch == "a1b2c3d"


def test_fetch_dev_tiles_clean(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    git_dir = repo_dir / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/master\n", encoding="utf-8")

    monkeypatch.setattr(dev_source, "get_git_dirty_count", lambda root, timeout=1.5: 0)

    cfg = {"sources": {"dev": {"repoPath": str(repo_dir)}}}
    tiles = dev_source.fetch_dev_tiles(cfg)

    assert len(tiles) == 1
    t = tiles[0]
    assert t["id"] == "git:branch"
    assert t["source"] == "dev"
    assert t["name"] == "Git"
    assert t["center_text"] == "master"
    assert t["sub_text"] == "🌿 master (clean)"
    assert t["ratio"] == 1.0
    assert t["dirty_count"] == 0
    assert t["repo_path"] == str(repo_dir.resolve())


def test_fetch_dev_tiles_dirty(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    git_dir = repo_dir / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/dev-branch\n", encoding="utf-8")

    monkeypatch.setattr(dev_source, "get_git_dirty_count", lambda root, timeout=1.5: 3)

    cfg = {"sources": {"dev": {"repoPath": str(repo_dir)}}}
    tiles = dev_source.fetch_dev_tiles(cfg)

    assert len(tiles) == 1
    t = tiles[0]
    assert t["id"] == "git:branch"
    assert t["sub_text"] == "🌿 dev-branch (+3)"
    assert t["dirty_count"] == 3


def test_fetch_dev_tiles_not_in_repo(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    cfg = {"sources": {"dev": {"repoPath": str(empty_dir)}}}
    tiles = dev_source.fetch_dev_tiles(cfg)
    assert len(tiles) == 1
    assert "未检测到仓库" in tiles[0]["sub_text"]


def test_open_repo_terminal_invalid_path():
    assert dev_source.open_repo_terminal("Z:/non_existent_path_xyz") is False
