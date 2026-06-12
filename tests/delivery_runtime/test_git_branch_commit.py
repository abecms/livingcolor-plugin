"""Tests for committing pending delivery work before publication."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from delivery_runtime.development.git_branch import commit_delivery_work


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@example.com")


def _git(workspace: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def delivery_workspace(tmp_path: Path) -> Path:
    """Tmp git repo checked out on the delivery branch at baseline."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    (workspace / "README.md").write_text("hello\n", encoding="utf-8")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "-m", "init")
    _git(workspace, "checkout", "-b", "feature/TVP-1489")
    return workspace


def test_commits_staged_and_unstaged_work(delivery_workspace: Path):
    (delivery_workspace / "staged.txt").write_text("staged\n", encoding="utf-8")
    _git(delivery_workspace, "add", "staged.txt")
    (delivery_workspace / "unstaged.txt").write_text("unstaged\n", encoding="utf-8")
    (delivery_workspace / "README.md").write_text("hello edited\n", encoding="utf-8")

    created = commit_delivery_work(
        delivery_workspace,
        branch="feature/TVP-1489",
        message="TVP-1489: fix front",
    )

    assert created is True
    assert _git(delivery_workspace, "status", "--porcelain") == ""
    files = _git(delivery_workspace, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert {"staged.txt", "unstaged.txt", "README.md"} <= set(files)


def test_clean_tree_returns_false_without_commit(delivery_workspace: Path):
    head_before = _git(delivery_workspace, "rev-parse", "HEAD")

    created = commit_delivery_work(
        delivery_workspace,
        branch="feature/TVP-1489",
        message="TVP-1489: fix front",
    )

    assert created is False
    assert _git(delivery_workspace, "rev-parse", "HEAD") == head_before


def test_wrong_current_branch_raises(delivery_workspace: Path):
    _git(delivery_workspace, "checkout", "main")
    (delivery_workspace / "stray.txt").write_text("stray\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="feature/TVP-1489"):
        commit_delivery_work(
            delivery_workspace,
            branch="feature/TVP-1489",
            message="TVP-1489: fix front",
        )
    # Nothing was committed on the wrong branch.
    assert "stray.txt" not in _git(delivery_workspace, "show", "--name-only", "--format=", "HEAD")


def test_commit_message_used_verbatim(delivery_workspace: Path):
    (delivery_workspace / "work.txt").write_text("work\n", encoding="utf-8")

    commit_delivery_work(
        delivery_workspace,
        branch="feature/TVP-1489",
        message="TVP-1489: Fix OAuth callback — verbatim title",
    )

    assert _git(delivery_workspace, "log", "-1", "--format=%s") == (
        "TVP-1489: Fix OAuth callback — verbatim title"
    )
