"""Merge conflict detection helpers for delivery development."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from delivery_runtime.development.git_branch import (
    DEFAULT_MERGE_TARGET_BRANCHES,
    resolve_merge_target_branch,
)
from delivery_runtime.shadow.context import allow_internal_git


@dataclass(frozen=True)
class MergeAttemptResult:
    ok: bool
    merge_target_branch: str | None = None
    feature_branch: str | None = None
    conflicting_files: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def integration_branch(self) -> str | None:
        """Backward-compatible alias (pre–merge-target policy)."""
        return self.merge_target_branch


def list_conflicting_files(workspace: Path) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )
    files = [line.strip() for line in (result.stdout or "").strip().splitlines() if line.strip()]
    if files:
        return files

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )
    conflicting: list[str] = []
    for line in (status.stdout or "").splitlines():
        if len(line) >= 4 and line[0] in {"U", "A", "D"} and line[1] in {"U", "A", "D"}:
            conflicting.append(line[3:].strip())
    return conflicting


def workspace_has_merge_conflicts(workspace: Path) -> bool:
    return bool(list_conflicting_files(workspace))


def _current_branch(workspace: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )
    branch = (result.stdout or "").strip()
    if not branch:
        raise ValueError("Workspace is not on a named branch")
    return branch


def attempt_merge_into_target_branch(
    workspace: Path,
    *,
    merge_target_branches: tuple[str, ...] = DEFAULT_MERGE_TARGET_BRANCHES,
    feature_branch: str | None = None,
) -> MergeAttemptResult:
    """Simulate merging the delivery feature branch into the test-environment target branch."""
    if not (workspace / ".git").exists():
        return MergeAttemptResult(ok=False, message="Workspace is not a git repository")

    try:
        merge_target = resolve_merge_target_branch(workspace, merge_target_branches)
    except ValueError as exc:
        return MergeAttemptResult(ok=False, message=str(exc))

    try:
        feature = feature_branch or _current_branch(workspace)
    except ValueError as exc:
        return MergeAttemptResult(ok=False, merge_target_branch=merge_target, message=str(exc))

    with allow_internal_git():
        checkout_feature = subprocess.run(
            ["git", "checkout", feature],
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
        )
        if checkout_feature.returncode != 0:
            return MergeAttemptResult(
                ok=False,
                merge_target_branch=merge_target,
                feature_branch=feature,
                message=(checkout_feature.stderr or checkout_feature.stdout or "Checkout failed").strip(),
            )

        checkout_target = subprocess.run(
            ["git", "checkout", merge_target],
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
        )
        if checkout_target.returncode != 0:
            return MergeAttemptResult(
                ok=False,
                merge_target_branch=merge_target,
                feature_branch=feature,
                message=(checkout_target.stderr or checkout_target.stdout or "Checkout failed").strip(),
            )

        result = subprocess.run(
            ["git", "merge", "--no-commit", "--no-ff", feature],
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
        )

        conflicting = list_conflicting_files(workspace)
        if result.returncode != 0 or conflicting:
            subprocess.run(["git", "merge", "--abort"], cwd=workspace, check=False, capture_output=True, text=True)
            subprocess.run(["git", "checkout", feature], cwd=workspace, check=False, capture_output=True, text=True)
            return MergeAttemptResult(
                ok=False,
                merge_target_branch=merge_target,
                feature_branch=feature,
                conflicting_files=conflicting,
                message=(result.stderr or result.stdout or "Merge conflict detected").strip(),
            )

        subprocess.run(["git", "merge", "--abort"], cwd=workspace, check=False, capture_output=True, text=True)
        subprocess.run(["git", "checkout", feature], cwd=workspace, check=False, capture_output=True, text=True)

    return MergeAttemptResult(
        ok=True,
        merge_target_branch=merge_target,
        feature_branch=feature,
        message="Merge into test target branch is clean",
    )


def attempt_merge_integration_branch(
    workspace: Path,
    integration_branches: tuple[str, ...] = DEFAULT_MERGE_TARGET_BRANCHES,
) -> MergeAttemptResult:
    """Backward-compatible alias — simulates MR merge into the test-environment branch."""
    return attempt_merge_into_target_branch(workspace, merge_target_branches=integration_branches)
