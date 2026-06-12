"""Strict workspace confinement for Hermes Developer Agent runs (Phase 3G)."""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from delivery_runtime.development.path_tokens import (
    extract_command_path_arguments,
    is_allowed_readonly_skill_path,
    is_allowed_work_order_artifact_path,
    is_hard_blocked_path,
    should_ignore_path_token,
    terminal_path_access,
)
from delivery_runtime.development.workspace_access_audit import (
    clear_workspace_access_trace,
    record_workspace_access,
)

logger = logging.getLogger(__name__)

WORKSPACE_VIOLATION = "WORKSPACE_VIOLATION"
_WORKSPACE_EXPANSION_PREFIX = "Workspace confinement violation:"

WorkspaceTool = Literal["terminal", "file"]
PathAccess = Literal["read", "write"]

_guard_lock = threading.Lock()
_active_guards: dict[str, WorkspaceConfinementGuard] = {}


@dataclass
class WorkspaceConfinementGuard:
    workspace_root: Path
    task_id: str
    blocked: bool = False
    block_reason: str = ""
    violation_events: list[dict[str, str]] = field(default_factory=list)

    @property
    def workspace_root_text(self) -> str:
        return str(self.workspace_root.resolve())

    @property
    def artifact_root(self) -> Path:
        return self.workspace_root.resolve().parent

    def assert_path_allowed(
        self,
        path: str,
        *,
        tool: WorkspaceTool = "file",
        access: PathAccess = "write",
    ) -> str | None:
        if self.blocked:
            return self._blocked_message()
        allowed, resolved_text, reason = self._evaluate_path(path, tool=tool, access=access)
        if allowed:
            record_workspace_access(
                allowed=True,
                task_id=self.task_id,
                path=path,
                resolved_path=resolved_text,
                reason=reason,
                tool=tool,
            )
            return None
        record_workspace_access(
            allowed=False,
            task_id=self.task_id,
            path=path,
            resolved_path=resolved_text,
            reason=reason,
            tool=tool,
        )
        if reason in {"hard_blocked_path", "outside_workspace"}:
            return self.block(f"Path is outside workspace root: {path}")
        return self.block(reason)

    def check_terminal_before(self, command: str) -> str | None:
        if self.blocked:
            return self._blocked_message()
        normalized = (command or "").strip()
        if not normalized:
            return None
        if _attempts_parent_escape(normalized):
            record_workspace_access(
                allowed=False,
                task_id=self.task_id,
                path=normalized,
                resolved_path="",
                reason="shell_parent_escape",
                tool="terminal",
            )
            return self.block("Shell command attempts to leave the workspace root.")
        for token_path in extract_command_path_arguments(normalized):
            access = terminal_path_access(normalized, token_path)
            message = self.assert_path_allowed(token_path, tool="terminal", access=access)
            if message:
                return message
        return None

    def block(self, reason: str) -> str:
        self.blocked = True
        self.block_reason = reason
        self.violation_events.append({"reason": reason, "outcome": WORKSPACE_VIOLATION})
        logger.warning("Workspace confinement blocked development: %s", reason)
        return self._format_message(reason)

    def _evaluate_path(
        self,
        path: str,
        *,
        tool: WorkspaceTool,
        access: PathAccess = "write",
    ) -> tuple[bool, str, str]:
        cleaned = (path or "").strip()
        if should_ignore_path_token(cleaned):
            return True, str(self.workspace_root.resolve()), "ignored_path_token"
        if access == "read" and is_allowed_readonly_skill_path(cleaned):
            resolved = _safe_resolve_text(cleaned, self.workspace_root)
            return True, resolved, "readonly_skill_path"
        if is_hard_blocked_path(cleaned):
            resolved = _safe_resolve_text(cleaned, self.workspace_root)
            return False, resolved, "hard_blocked_path"
        resolved_path = resolve_checked_path(cleaned, self.workspace_root, self.task_id)
        if resolved_path is None:
            resolved = _safe_resolve_text(cleaned, self.workspace_root)
            return False, resolved, "outside_workspace"
        if is_allowed_work_order_artifact_path(resolved_path, self.workspace_root):
            return True, str(resolved_path.resolve()), "allowed_work_order_artifact"
        return True, str(resolved_path.resolve()), "inside_workspace"

    def _blocked_message(self) -> str:
        return self._format_message(self.block_reason or "Development halted by workspace confinement.")

    @staticmethod
    def _format_message(reason: str) -> str:
        if reason.startswith(_WORKSPACE_EXPANSION_PREFIX):
            return reason
        return f"{_WORKSPACE_EXPANSION_PREFIX} {reason}"


def register_workspace_confinement(task_id: str, workspace_root: Path) -> WorkspaceConfinementGuard:
    guard = WorkspaceConfinementGuard(workspace_root=workspace_root.resolve(), task_id=task_id)
    with _guard_lock:
        _active_guards[task_id] = guard
    return guard


def clear_workspace_confinement(task_id: str) -> None:
    with _guard_lock:
        _active_guards.pop(task_id, None)
    clear_workspace_access_trace(task_id)


def get_workspace_confinement(task_id: str | None) -> WorkspaceConfinementGuard | None:
    if not task_id:
        return None
    with _guard_lock:
        return _active_guards.get(task_id)


def activate_workspace_runtime(
    task_id: str,
    workspace_root: Path,
    *,
    confinement_root: Path | None = None,
) -> tuple[str | None, object | None]:
    """Pin process/runtime cwd carriers to the checkout; confine paths to confinement_root."""
    workspace_text = str(workspace_root.resolve())
    confinement_text = str((confinement_root or workspace_root).resolve())
    previous_terminal_cwd = os.environ.get("TERMINAL_CWD")
    os.environ["TERMINAL_CWD"] = workspace_text
    session_token = None
    try:
        from agent.runtime_cwd import set_session_cwd

        session_token = set_session_cwd(workspace_text)
    except Exception:
        session_token = None
    clear_workspace_access_trace(task_id)
    register_workspace_confinement(task_id, Path(confinement_text))
    return previous_terminal_cwd, session_token


def deactivate_workspace_runtime(
    task_id: str,
    *,
    previous_terminal_cwd: str | None,
    session_token: object | None,
) -> None:
    clear_workspace_confinement(task_id)
    if previous_terminal_cwd is None:
        os.environ.pop("TERMINAL_CWD", None)
    else:
        os.environ["TERMINAL_CWD"] = previous_terminal_cwd
    if session_token is not None:
        try:
            from agent.runtime_cwd import clear_session_cwd

            clear_session_cwd()
        except Exception:
            pass


def check_delivery_workspace_tool(task_id: str | None, tool_name: str, args: dict) -> str | None:
    guard = get_workspace_confinement(task_id)
    if guard is None:
        return None
    if tool_name in {"skill_view", "skills_list", "check_skills_requirements"}:
        return None
    file_read_tools = {"read_file", "search_files"}
    file_write_tools = {"write_file", "patch"}
    if tool_name in file_read_tools | file_write_tools:
        access: PathAccess = "read" if tool_name in file_read_tools else "write"
        if tool_name == "patch":
            paths: list[str] = []
            if args.get("path"):
                paths.append(str(args["path"]))
            patch_text = str(args.get("patch") or "")
            for match in re.finditer(
                r"^\*\*\*\s+(?:Update|Add|Delete)\s+File:\s*(.+)$",
                patch_text,
                re.MULTILINE,
            ):
                paths.append(match.group(1).strip())
            for path in paths:
                message = guard.assert_path_allowed(path, tool="file", access="write")
                if message:
                    return message
            return None
        path = str(args.get("path") or args.get("query") or "")
        if path:
            return guard.assert_path_allowed(path, tool="file", access=access)
    if tool_name == "terminal":
        return guard.check_terminal_before(str(args.get("command") or ""))
    return None


def resolve_confined_path(path: str, workspace_root: Path, task_id: str | None = None) -> str | None:
    cleaned = (path or "").strip().replace("\\", "/")
    if should_ignore_path_token(cleaned):
        return "."
    resolved = resolve_checked_path(cleaned, workspace_root, task_id)
    if resolved is None:
        return None
    workspace = workspace_root.resolve()
    try:
        relative = resolved.relative_to(workspace)
        return str(relative).replace("\\", "/") if str(relative) != "." else "."
    except ValueError:
        relative = resolved.relative_to(workspace.parent)
        return f"@artifact/{relative}".replace("\\", "/")


def resolve_checked_path(path: str, workspace_root: Path, task_id: str | None = None) -> Path | None:
    absolute = resolve_absolute_path(path, workspace_root, task_id)
    if absolute is None:
        return None
    workspace = workspace_root.resolve()
    try:
        absolute.relative_to(workspace)
        return absolute
    except ValueError:
        pass
    if is_allowed_work_order_artifact_path(absolute, workspace):
        return absolute
    return None


def resolve_absolute_path(path: str, workspace_root: Path, task_id: str | None = None) -> Path | None:
    del task_id  # Confinement always anchors relative paths to the workspace root.
    cleaned = (path or "").strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if should_ignore_path_token(cleaned):
        return workspace_root.resolve()
    candidate = Path(cleaned).expanduser()
    if not candidate.is_absolute():
        return (workspace_root.resolve() / candidate).resolve()
    return candidate.resolve()


def confined_base_dir(task_id: str) -> Path | None:
    guard = get_workspace_confinement(task_id)
    if guard is None:
        return None
    return guard.workspace_root


def _safe_resolve_text(path: str, workspace_root: Path) -> str:
    try:
        return str(resolve_absolute_path(path, workspace_root) or "")
    except OSError:
        return ""


def _attempts_parent_escape(command: str) -> bool:
    lowered = command.lower()
    if re.search(r"(?:^|\s)cd\s+\.\.", lowered):
        return True
    if re.search(r"(?:^|\s)cd\s+/\s*$", lowered):
        return True
    return False


__all__ = [
    "WORKSPACE_VIOLATION",
    "WorkspaceConfinementGuard",
    "activate_workspace_runtime",
    "check_delivery_workspace_tool",
    "clear_workspace_confinement",
    "confined_base_dir",
    "deactivate_workspace_runtime",
    "get_workspace_confinement",
    "register_workspace_confinement",
    "resolve_confined_path",
]
