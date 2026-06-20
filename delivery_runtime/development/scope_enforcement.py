"""Hard Scope Contract enforcement during Hermes development (Phase 3F)."""

from __future__ import annotations

import logging
import re
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from delivery_runtime.development.command_policy import evaluate_terminal_command, extract_command_paths
from delivery_runtime.development.path_tokens import (
    is_allowed_readonly_skill_path,
    should_ignore_path_token,
    terminal_path_access,
)
from delivery_runtime.development.scope_contract import ScopeContract, is_ephemeral_side_effect_path
from delivery_runtime.development.scope_validator import check_path_against_contract, is_workspace_nav_path
from delivery_runtime.shadow.context import allow_internal_git

logger = logging.getLogger(__name__)

SCOPE_VIOLATION_BLOCKED = "SCOPE_VIOLATION_BLOCKED"
_SCOPE_EXPANSION_PREFIX = "Scope expansion required:"

_guard_lock = threading.Lock()
_active_guards: dict[str, ScopeEnforcementGuard] = {}


@dataclass
class ScopeEnforcementGuard:
    contract: ScopeContract
    workspace: Path
    baseline_ref: str | None
    task_id: str = ""
    allow_dependency_update: bool = False
    allow_git_write: bool = False
    allow_git_push: bool = False
    blocked: bool = False
    block_outcome: str = ""
    block_reason: str = ""
    blocked_paths: list[str] = field(default_factory=list)
    block_events: list[dict[str, str]] = field(default_factory=list)

    def check_write_path(self, path: str) -> str | None:
        if self.blocked:
            return self._blocked_message()
        rel = resolve_workspace_relative_path(path, self.workspace, self.task_id)
        if rel is None:
            return self.block(
                path,
                f"Path is outside the development workspace sandbox: {path}",
            )
        if is_workspace_nav_path(rel):
            return None
        violation = check_path_against_contract(rel, self.contract)
        if violation:
            return self.block(rel, violation)
        return None

    def check_terminal_before(self, command: str) -> str | None:
        if self.blocked:
            return self._blocked_message()
        policy = evaluate_terminal_command(
            command,
            allow_dependency_update=self.allow_dependency_update,
            allow_git_write=self.allow_git_write,
            allow_git_push=self.allow_git_push,
        )
        if policy.decision == "deny":
            return self.block("terminal", policy.reason or "Terminal command denied by scope policy.")
        for token_path in extract_command_paths(command):
            if _skip_terminal_path_scope_check(command, token_path):
                continue
            rel = resolve_workspace_relative_path(token_path, self.workspace, self.task_id)
            if rel is None:
                return self.block(token_path, f"Command targets path outside workspace: {token_path}")
            if is_workspace_nav_path(rel):
                continue
            if is_ephemeral_side_effect_path(rel):
                continue
            violation = check_path_against_contract(rel, self.contract)
            if violation:
                return self.block(rel, violation)
        return None

    def snapshot_touched_paths(self) -> list[str]:
        return _git_changed_paths(self.workspace, self.baseline_ref)

    def post_terminal_after(self, command: str) -> str | None:
        if self.blocked:
            return self._blocked_message()
        self._restore_ephemeral_side_effects()
        touched = self.snapshot_touched_paths()
        violations = self._violations_for_paths(touched)
        if violations:
            self.rollback_to_clean()
            reason = (
                f"Terminal command modified forbidden or out-of-scope paths: "
                f"{', '.join(violations[:5])}"
            )
            return self.block(violations[0], reason)
        return None

    def block(self, path_or_label: str, reason: str, *, outcome: str = SCOPE_VIOLATION_BLOCKED) -> str:
        self.blocked = True
        self.block_outcome = outcome
        self.block_reason = reason
        if path_or_label not in self.blocked_paths:
            self.blocked_paths.append(path_or_label)
        self.block_events.append({"path": path_or_label, "reason": reason, "outcome": outcome})
        logger.warning("Scope enforcement blocked development: %s", reason)
        return self._format_block_message(reason)

    def rollback_to_clean(self) -> None:
        with allow_internal_git():
            if self.baseline_ref:
                subprocess.run(
                    ["git", "checkout", self.baseline_ref, "--", "."],
                    cwd=self.workspace,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "clean", "-fd"],
                    cwd=self.workspace,
                    check=False,
                    capture_output=True,
                    text=True,
                )
            else:
                subprocess.run(
                    ["git", "checkout", "--", "."],
                    cwd=self.workspace,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "clean", "-fd"],
                    cwd=self.workspace,
                    check=False,
                    capture_output=True,
                    text=True,
                )

    def cleanup_forbidden_artifacts(self) -> tuple[bool, list[str]]:
        """Remove forbidden generated artifacts before patch collection."""
        self._restore_ephemeral_side_effects()
        touched = self.snapshot_touched_paths()
        violations = self._violations_for_paths(touched)
        if not violations:
            return True, []
        self.rollback_to_clean()
        self._restore_ephemeral_side_effects()
        remaining = self._violations_for_paths(self.snapshot_touched_paths())
        return not remaining, remaining

    def _restore_ephemeral_side_effects(self) -> None:
        touched = self.snapshot_touched_paths()
        ephemeral = [path for path in touched if is_ephemeral_side_effect_path(path)]
        if not ephemeral:
            return
        with allow_internal_git():
            if self.baseline_ref:
                subprocess.run(
                    ["git", "checkout", self.baseline_ref, "--", *ephemeral],
                    cwd=self.workspace,
                    check=False,
                    capture_output=True,
                    text=True,
                )
            else:
                subprocess.run(
                    ["git", "checkout", "--", *ephemeral],
                    cwd=self.workspace,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "clean", "-fd", "--", *ephemeral],
                    cwd=self.workspace,
                    check=False,
                    capture_output=True,
                    text=True,
                )

    def _violations_for_paths(self, paths: list[str]) -> list[str]:
        violations: list[str] = []
        for path in paths:
            rel = workspace_relative_git_path(path, self.workspace)
            if rel is None or is_workspace_nav_path(rel):
                continue
            if is_ephemeral_side_effect_path(rel):
                continue
            message = check_path_against_contract(rel, self.contract)
            if message:
                violations.append(rel)
        return violations

    def _blocked_message(self) -> str:
        return self._format_block_message(self.block_reason or "Development halted by scope enforcement.")

    @staticmethod
    def _format_block_message(reason: str) -> str:
        if reason.startswith(_SCOPE_EXPANSION_PREFIX):
            return reason
        return f"{_SCOPE_EXPANSION_PREFIX} {reason}"


def register_scope_guard(task_id: str, guard: ScopeEnforcementGuard) -> None:
    with _guard_lock:
        _active_guards[task_id] = guard


def clear_scope_guard(task_id: str) -> None:
    with _guard_lock:
        _active_guards.pop(task_id, None)


def get_scope_guard(task_id: str | None) -> ScopeEnforcementGuard | None:
    if not task_id:
        return None
    with _guard_lock:
        return _active_guards.get(task_id)


def guard_from_context(
    *,
    task_id: str,
    workspace: Path,
    baseline_ref: str | None,
    scope_contract: dict[str, Any] | None,
    allow_git_write: bool = False,
    allow_git_push: bool = False,
) -> ScopeEnforcementGuard | None:
    if not scope_contract:
        return None
    contract = ScopeContract.from_dict(scope_contract)
    allow_dependency_update = bool(scope_contract.get("allowDependencyUpdate")) or bool(
        scope_contract.get("workspaceOnly")
    )
    guard = ScopeEnforcementGuard(
        contract=contract,
        workspace=workspace,
        baseline_ref=baseline_ref,
        task_id=task_id,
        allow_dependency_update=allow_dependency_update,
        allow_git_write=allow_git_write,
        allow_git_push=allow_git_push,
    )
    register_scope_guard(task_id, guard)
    return guard


def check_delivery_tool_scope(task_id: str | None, tool_name: str, args: dict[str, Any]) -> str | None:
    guard = get_scope_guard(task_id)
    if guard is None:
        return None

    if tool_name == "write_file":
        path = str(args.get("path") or "")
        return guard.check_write_path(path)

    if tool_name == "patch":
        paths: list[str] = []
        if args.get("path"):
            paths.append(str(args["path"]))
        patch_text = str(args.get("patch") or "")
        if patch_text:
            for match in re.finditer(
                r"^\*\*\*\s+(?:Update|Add|Delete)\s+File:\s*(.+)$",
                patch_text,
                re.MULTILINE,
            ):
                paths.append(match.group(1).strip())
        for path in paths:
            message = guard.check_write_path(path)
            if message:
                return message
        return None

    if tool_name == "terminal":
        command = str(args.get("command") or "")
        return guard.check_terminal_before(command)

    return None


def post_delivery_terminal_scope(task_id: str | None, command: str) -> str | None:
    guard = get_scope_guard(task_id)
    if guard is None:
        return None
    return guard.post_terminal_after(command)


def _skip_terminal_path_scope_check(command: str, token_path: str) -> bool:
    """Ignore shell pseudo-paths and read-only skill loads during scope checks."""
    if should_ignore_path_token(token_path):
        return True
    if is_allowed_readonly_skill_path(token_path) and terminal_path_access(command, token_path) == "read":
        return True
    return False


def resolve_workspace_relative_path(path: str, workspace: Path, task_id: str | None = None) -> str | None:
    cleaned = (path or "").strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if task_id:
        resolved = workspace_relative_git_path(cleaned, workspace)
        if resolved:
            return resolved
    return workspace_relative_git_path(cleaned, workspace)


def workspace_relative_git_path(path: str, workspace: Path) -> str | None:
    candidate = Path(path)
    workspace_root = workspace.resolve()
    if not candidate.is_absolute():
        candidate = (workspace_root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    try:
        rel = candidate.relative_to(workspace_root)
        return str(rel).replace("\\", "/")
    except ValueError:
        return None


def _git_changed_paths(workspace: Path, baseline_ref: str | None) -> list[str]:
    with allow_internal_git():
        if baseline_ref:
            result = subprocess.run(
                ["git", "diff", "--name-only", baseline_ref],
                cwd=workspace,
                check=False,
                capture_output=True,
                text=True,
            )
        else:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=workspace,
                check=False,
                capture_output=True,
                text=True,
            )
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=workspace,
                check=False,
                capture_output=True,
                text=True,
            )
    paths = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    filtered: list[str] = []
    for path in paths:
        rel = workspace_relative_git_path(path, workspace)
        if rel and rel != ".":
            filtered.append(rel)
    return list(dict.fromkeys(filtered))
