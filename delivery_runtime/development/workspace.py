"""Shared development workspace helpers (Hermes-free)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from delivery_runtime.context.repo_checkout import fetch_managed_checkout, is_managed_repo_checkout
from delivery_runtime.shadow.context import allow_internal_git
from delivery_runtime.shadow.paths import get_work_order_artifact_root


def prepare_development_workspace(
    work_order_id: str,
    checkout_path: str,
    *,
    jira_key: str | None = None,
    issue_type: str = "",
    reuse_existing: bool = False,
    baseline_ref: str | None = None,
) -> tuple[Path, str | None]:
    """Prepare an isolated work-order workspace and record a diff baseline.

    Managed LivingColor checkouts (``~/.livingcolor/{PROJECT}/…``) are used
    in-place — no ``copytree`` per Work Order. Arbitrary external paths still
    copy into ``work_orders/{WO}/workspace`` for isolation.
    """
    checkout = Path(checkout_path).expanduser().resolve()
    shared_checkout = is_managed_repo_checkout(checkout)
    root = checkout if shared_checkout else get_work_order_artifact_root(work_order_id) / "workspace"

    if reuse_existing and root.exists():
        return root, baseline_ref or _git_head(root)

    if shared_checkout and not reuse_existing and (root / ".git").exists():
        fetch_managed_checkout(root)

    if not shared_checkout:
        if root.exists():
            shutil.rmtree(root)
        shutil.copytree(checkout_path, root, dirs_exist_ok=True)

    if jira_key and (root / ".git").exists():
        from delivery_runtime.development.git_branch import ensure_delivery_branch

        ensure_delivery_branch(
            root,
            jira_key=jira_key,
            issue_type=issue_type,
        )

    if not (root / ".git").exists():
        with allow_internal_git():
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=False, capture_output=True, text=True)
            subprocess.run(["git", "add", "-A"], cwd=root, check=False, capture_output=True, text=True)
            subprocess.run(
                ["git", "commit", "-m", "livingcolor-baseline"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
        if jira_key:
            from delivery_runtime.development.git_branch import ensure_delivery_branch

            ensure_delivery_branch(
                root,
                jira_key=jira_key,
                issue_type=issue_type,
            )

    baseline = _git_head(root)
    return root, baseline


def collect_patch_from_workspace(
    workspace: Path,
    baseline_ref: str | None,
    *,
    scope_guard: Any | None = None,
) -> tuple[str, dict[str, int], list[str], list[str], list[str]]:
    """Collect git diff and touched file lists relative to the workspace baseline."""
    if scope_guard is not None:
        clean_ok, remaining = scope_guard.cleanup_forbidden_artifacts()
        if not clean_ok:
            return "", {"linesAdded": 0, "linesRemoved": 0, "linesChanged": 0, "filesChanged": 0}, [], [], []

    subprocess.run(["git", "add", "-A"], cwd=workspace, check=False, capture_output=True, text=True)

    with allow_internal_git():
        if baseline_ref:
            diff_cmd = ["git", "diff", "--cached", "--stat", "--patch", baseline_ref]
            name_status_cmd = ["git", "diff", "--name-status", baseline_ref]
        else:
            diff_cmd = ["git", "diff", "--cached", "--stat", "--patch"]
            name_status_cmd = ["git", "diff", "--cached", "--name-status"]

        diff_result = subprocess.run(diff_cmd, cwd=workspace, check=False, capture_output=True, text=True)
        diff_text = diff_result.stdout or ""

        status_result = subprocess.run(
            name_status_cmd,
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
        )
    modified: list[str] = []
    created: list[str] = []
    deleted: list[str] = []
    for line in (status_result.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0].strip(), parts[-1].strip()
        if status.startswith("R") and len(parts) >= 3:
            path = parts[-1]
            modified.append(path)
            continue
        if status == "A":
            created.append(path)
        elif status == "D":
            deleted.append(path)
        elif status in {"M", "T"}:
            modified.append(path)
        elif status.startswith("R"):
            modified.append(path)

    patch_stats = _patch_stats(diff_text)
    return diff_text, patch_stats, modified, created, deleted


def _git_head(workspace: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )
    sha = (result.stdout or "").strip()
    return sha or None


def _patch_stats(diff_text: str) -> dict[str, int]:
    lines_added = len(re.findall(r"^\+[^+]", diff_text, flags=re.MULTILINE))
    lines_removed = len(re.findall(r"^-[^-]", diff_text, flags=re.MULTILINE))
    files_changed = len(re.findall(r"^\s*file changed", diff_text, flags=re.MULTILINE))
    return {
        "filesChanged": files_changed,
        "linesAdded": lines_added,
        "linesRemoved": lines_removed,
        "linesChanged": lines_added + lines_removed,
    }
