"""Tests for delivery git branch naming and checkout."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from delivery_runtime.development.git_branch import (
    branch_prefix_for_issue_type,
    ensure_delivery_branch,
    format_delivery_branch_name,
    resolve_integration_branch,
    resolve_merge_target_branch,
)

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def _git_init_main(workspace: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True, text=True)
    (workspace / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
        env=_GIT_ENV,
    )


@pytest.mark.parametrize(
    ("issue_type", "expected"),
    [
        ("Bug", "fix"),
        ("bug", "fix"),
        ("Hotfix", "fix"),
        ("Story", "feature"),
        ("Task", "feature"),
        ("Improvement", "feature"),
        ("", "feature"),
    ],
)
def test_branch_prefix_for_issue_type(issue_type, expected):
    assert branch_prefix_for_issue_type(issue_type) == expected


@pytest.mark.parametrize(
    ("jira_key", "issue_type", "expected"),
    [
        ("TVP-1022", "Story", "feature/TVP-1022"),
        ("TVP-1022", "Bug", "fix/TVP-1022"),
        ("tvp-999", "Task", "feature/TVP-999"),
    ],
)
def test_format_delivery_branch_name(jira_key, issue_type, expected):
    assert format_delivery_branch_name(jira_key, issue_type) == expected


def _git_init_main_with_staging(workspace: Path) -> None:
    _git_init_main(workspace)
    subprocess.run(["git", "checkout", "-b", "staging"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "main"], cwd=workspace, check=True, capture_output=True, text=True)


def test_ensure_delivery_branch_creates_feature_branch_from_main(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _git_init_main_with_staging(workspace)

    branch_name, base_branch, merge_target = ensure_delivery_branch(
        workspace,
        jira_key="TVP-1022",
        issue_type="Story",
    )

    assert base_branch == "main"
    assert merge_target == "staging"
    assert branch_name == "feature/TVP-1022"
    current = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    assert current.stdout.strip() == "feature/TVP-1022"


def test_resolve_merge_target_branch_prefers_staging(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _git_init_main_with_staging(workspace)
    assert resolve_merge_target_branch(workspace) == "staging"


def test_resolve_integration_branch_prefers_main(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _git_init_main(workspace)
    assert resolve_integration_branch(workspace) == "main"
