"""Git branch naming and checkout helpers for delivery development."""

from __future__ import annotations

import subprocess
from pathlib import Path

from delivery_runtime.shadow.context import allow_internal_git

DEFAULT_INTEGRATION_BRANCHES = ("main", "master", "prod")
DEFAULT_MERGE_TARGET_BRANCHES = ("staging", "dev", "develop", "preprod", "test")

FIX_ISSUE_TYPES = frozenset({"bug", "defect", "hotfix", "incident"})
FEATURE_ISSUE_TYPES = frozenset(
    {
        "story",
        "task",
        "feature",
        "improvement",
        "epic",
        "sub-task",
        "subtask",
        "spike",
        "enhancement",
        "evolution",
    }
)


def branch_prefix_for_issue_type(issue_type: str) -> str:
    """Return ``fix`` for corrective work, ``feature`` for evolutions."""
    normalized = (issue_type or "").strip().lower()
    if not normalized:
        return "feature"
    if normalized in FIX_ISSUE_TYPES:
        return "fix"
    if normalized in FEATURE_ISSUE_TYPES:
        return "feature"
    if "bug" in normalized or "fix" in normalized or "defect" in normalized:
        return "fix"
    return "feature"


def format_delivery_branch_name(jira_key: str, issue_type: str = "") -> str:
    """Build the canonical delivery branch name for a Jira ticket."""
    key = (jira_key or "").strip().upper()
    if not key:
        raise ValueError("jira_key is required")
    prefix = branch_prefix_for_issue_type(issue_type)
    return f"{prefix}/{key}"


def resolve_integration_branch(
    workspace: Path,
    candidates: tuple[str, ...] = DEFAULT_INTEGRATION_BRANCHES,
) -> str:
    """Resolve the production-linked branch to create delivery branches from."""
    return _resolve_first_existing_branch(workspace, candidates, purpose="integration")


def resolve_merge_target_branch(
    workspace: Path,
    candidates: tuple[str, ...] = DEFAULT_MERGE_TARGET_BRANCHES,
) -> str:
    """Resolve the test-environment branch the delivery MR should merge into."""
    return _resolve_first_existing_branch(workspace, candidates, purpose="merge target")


def _resolve_first_existing_branch(
    workspace: Path,
    candidates: tuple[str, ...],
    *,
    purpose: str,
) -> str:
    with allow_internal_git():
        for branch in candidates:
            if _ref_exists(workspace, branch):
                return branch
        for branch in candidates:
            remote_ref = f"origin/{branch}"
            if _ref_exists(workspace, remote_ref):
                _run_git(["git", "checkout", "-B", branch, remote_ref], workspace)
                return branch
        for branch in candidates:
            fetched = _fetch_remote_branch(workspace, branch)
            if fetched and _ref_exists(workspace, branch):
                return branch
            remote_ref = f"origin/{branch}"
            if fetched and _ref_exists(workspace, remote_ref):
                _run_git(["git", "checkout", "-B", branch, remote_ref], workspace)
                return branch
    raise ValueError(
        f"No {purpose} branch found in {workspace}; expected one of: {', '.join(candidates)}"
    )


def _fetch_remote_branch(workspace: Path, branch: str) -> bool:
    """Best-effort fetch for a single branch (shallow clones often miss integration branches)."""
    branch = (branch or "").strip()
    if not branch:
        return False
    result = subprocess.run(
        ["git", "fetch", "--depth", "1", "origin", f"{branch}:refs/remotes/origin/{branch}"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True
    fallback = subprocess.run(
        ["git", "fetch", "--depth", "1", "origin", branch],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )
    return fallback.returncode == 0



def ensure_delivery_branch(
    workspace: Path,
    *,
    jira_key: str,
    issue_type: str = "",
    integration_branches: tuple[str, ...] = DEFAULT_INTEGRATION_BRANCHES,
) -> tuple[str, str, str | None]:
    """Create or reset the per-ticket branch from the production-linked integration branch.

    Returns ``(delivery_branch, integration_branch, merge_target_branch)``.
    ``merge_target_branch`` is ``None`` when no test-environment branch exists in the checkout.
    """
    branch_name = format_delivery_branch_name(jira_key, issue_type)
    base_branch = resolve_integration_branch(workspace, integration_branches)
    try:
        merge_target_branch: str | None = resolve_merge_target_branch(workspace)
    except ValueError:
        merge_target_branch = None
    with allow_internal_git():
        _run_git(["git", "checkout", base_branch], workspace)
        _run_git(["git", "checkout", "-B", branch_name], workspace)
    return branch_name, base_branch, merge_target_branch


def commit_delivery_work(workspace: Path, *, branch: str, message: str) -> bool:
    """Commit all pending work on the delivery branch before publication.

    Returns True if a commit was created, False if the tree was already clean.
    """
    expected = (branch or "").strip()
    if not expected:
        raise ValueError("branch is required")

    with allow_internal_git():
        current = _git_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], workspace)
        if current != expected:
            raise RuntimeError(
                f"workspace {workspace} is on branch {current!r}, expected delivery "
                f"branch {expected!r}; refusing to commit"
            )
        _run_git(["git", "add", "-A"], workspace)
        if not _git_output(["git", "status", "--porcelain"], workspace):
            return False
        _run_git(["git", "commit", "-m", message], workspace)
    return True


def _git_output(command: list[str], workspace: Path) -> str:
    result = subprocess.run(command, cwd=workspace, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Git command failed ({' '.join(command)}): {detail}")
    return (result.stdout or "").strip()


def _ref_exists(workspace: Path, ref: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _run_git(command: list[str], workspace: Path) -> None:
    result = subprocess.run(command, cwd=workspace, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Git command failed ({' '.join(command)}): {detail}")
