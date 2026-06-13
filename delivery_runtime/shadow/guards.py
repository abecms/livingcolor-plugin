"""Shadow mode side-effect guards and violation audit trail."""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from delivery_runtime.shadow.context import current_delivery_agent_role, internal_git_allowed
from delivery_runtime.shadow.mode import is_shadow_mode
from delivery_runtime.shadow.paths import get_evaluation_root

_BLOCKED_GIT_COMMANDS = ("push", "commit", "merge", "tag")
_BLOCKED_GIT_PATTERN = re.compile(
    r"(?:(?:^|[;&|]\s*)git\s+(?:-C\s+\S+\s+)?(?:[\w-]+\s+)*?(?:push|commit|merge|tag)\b)|"
    r"(?:^|[;&|]\s*)(?:git\s+)?(?:push|commit|merge|tag)\b",
    re.IGNORECASE,
)

_JIRA_WRITE_TOOLS = {
    "transition_issue",
    "transitionissue",
    "add_comment",
    "addcomment",
    "comment_issue",
    "commentissue",
    "update_issue",
    "updateissue",
    "create_issue",
    "createissue",
    "delete_issue",
    "deleteissue",
    "assign_issue",
    "assignissue",
}

_GITLAB_WRITE_TOOLS = {
    "create_branch",
    "createbranch",
    "create_merge_request",
    "createmergerequest",
    "update_merge_request",
    "updatemergerequest",
    "merge_merge_request",
    "mergemergerequest",
    "merge",
    "push",
}

_GITHUB_WRITE_TOOLS = {
    "create_pull_request",
    "createpullrequest",
    "create_branch",
    "createbranch",
    "create_ref",
    "createref",
    "update_pull_request",
    "updatepullrequest",
    "merge_pull_request",
    "mergepullrequest",
    "close_pull_request",
    "closepullrequest",
    "create_issue_comment",
    "createissuecomment",
    "push",
}

_MCP_WRITE_HINTS = (
    "create",
    "update",
    "delete",
    "transition",
    "comment",
    "merge",
    "push",
    "publish",
    "assign",
    "post_",
    "put_",
)

_MCP_READ_PREFIXES = (
    "get",
    "list",
    "search",
    "fetch",
    "read",
    "lookup",
    "find",
    "query",
    "describe",
)


@dataclass
class ShadowViolation:
    category: str
    operation: str
    detail: str
    blocked: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "operation": self.operation,
            "detail": self.detail,
            "blocked": self.blocked,
        }


@dataclass
class ShadowAuditLog:
    violations: list[ShadowViolation] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, violation: ShadowViolation) -> None:
        with self._lock:
            self.violations.append(violation)
        _append_violation_file(violation)

    def has_violations(self) -> bool:
        with self._lock:
            return bool(self.violations)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "violationCount": len(self.violations),
                "violations": [item.to_dict() for item in self.violations],
            }


_audit_log = ShadowAuditLog()


def get_shadow_audit_log() -> ShadowAuditLog:
    return _audit_log


def reset_shadow_audit_log() -> None:
    global _audit_log
    _audit_log = ShadowAuditLog()


def check_terminal_command(command: str) -> ShadowViolation | None:
    if not is_shadow_mode():
        return None
    if internal_git_allowed():
        return None
    normalized = (command or "").strip()
    if not normalized:
        return None
    if not _BLOCKED_GIT_PATTERN.search(normalized):
        return None
    for verb in _BLOCKED_GIT_COMMANDS:
        if re.search(rf"\b{verb}\b", normalized, flags=re.IGNORECASE):
            violation = ShadowViolation(
                category="git",
                operation=verb,
                detail=f"Blocked git {verb} in shadow mode: {normalized[:200]}",
            )
            _audit_log.record(violation)
            return violation
    return None


def check_mcp_tool(server_name: str, tool_name: str) -> ShadowViolation | None:
    normalized_server = (server_name or "").strip().lower()
    normalized_tool = _normalize_tool_name(tool_name)
    if not normalized_tool:
        return None

    if not is_shadow_mode():
        return _check_standard_mode_vcs_write(normalized_server, normalized_tool)

    if normalized_server in {"jira", "atlassian", "user-jira mcp", "user-jira_mcp"} or "jira" in normalized_server:
        if normalized_tool in _JIRA_WRITE_TOOLS or _looks_like_write_tool(normalized_tool):
            violation = ShadowViolation(
                category="jira",
                operation=normalized_tool,
                detail=f"Blocked Jira write MCP tool {tool_name} in shadow mode",
            )
            _audit_log.record(violation)
            return violation
        return None

    if "gitlab" in normalized_server:
        if _is_vcs_write_tool(normalized_tool, _GITLAB_WRITE_TOOLS):
            violation = ShadowViolation(
                category="gitlab",
                operation=normalized_tool,
                detail=f"Blocked GitLab write MCP tool {tool_name} in shadow mode",
            )
            _audit_log.record(violation)
            return violation
        return None

    if normalized_server == "github" or "github" in normalized_server:
        if _is_vcs_write_tool(normalized_tool, _GITHUB_WRITE_TOOLS):
            if current_delivery_agent_role() == "publisher":
                return None
            operation = _compact_tool_name(normalized_tool)
            violation = ShadowViolation(
                category="github",
                operation=operation,
                detail=f"Blocked GitHub write MCP tool {tool_name} in shadow mode",
            )
            _audit_log.record(violation)
            return violation
        return None

    if _looks_like_write_tool(normalized_tool) and not _looks_like_read_tool(normalized_tool):
        violation = ShadowViolation(
            category="mcp",
            operation=normalized_tool,
            detail=f"Blocked MCP write tool {server_name}/{tool_name} in shadow mode",
        )
        _audit_log.record(violation)
        return violation
    return None


def _check_standard_mode_vcs_write(
    normalized_server: str, normalized_tool: str
) -> ShadowViolation | None:
    """In standard mode, VCS write tools are reserved for the publisher agent."""
    if "gitlab" in normalized_server:
        category = "gitlab"
        write_tools = _GITLAB_WRITE_TOOLS
        label = "GitLab"
    elif normalized_server == "github" or "github" in normalized_server:
        category = "github"
        write_tools = _GITHUB_WRITE_TOOLS
        label = "GitHub"
    else:
        return None
    if not _is_vcs_write_tool(normalized_tool, write_tools):
        return None
    role = current_delivery_agent_role()
    if role == "publisher":
        return None
    operation = (
        _compact_tool_name(normalized_tool)
        if category == "github"
        else normalized_tool
    )
    violation = ShadowViolation(
        category=category,
        operation=operation,
        detail=(
            f"{label} write tools are reserved for the publisher agent "
            f"(current role: {role or 'none'})"
        ),
    )
    _audit_log.record(violation)
    return violation


def terminal_block_response(violation: ShadowViolation) -> dict[str, Any]:
    return {
        "output": "",
        "exit_code": -1,
        "error": violation.detail,
        "status": "blocked",
        "shadowMode": True,
        "shadowViolation": violation.to_dict(),
    }


def mcp_block_response(violation: ShadowViolation) -> dict[str, Any]:
    return {
        "error": violation.detail,
        "shadowMode": is_shadow_mode(),
        "shadowViolation": violation.to_dict(),
        "blocked": True,
    }


def _normalize_tool_name(tool_name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", (tool_name or "").strip().lower())


def _compact_tool_name(tool_name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", tool_name)


def _looks_like_read_tool(tool_name: str) -> bool:
    return any(tool_name.startswith(prefix) for prefix in _MCP_READ_PREFIXES)


def _looks_like_write_tool(tool_name: str) -> bool:
    if _looks_like_read_tool(tool_name):
        return False
    return any(hint in tool_name for hint in _MCP_WRITE_HINTS)


def _is_vcs_write_tool(tool_name: str, write_tools: set[str]) -> bool:
    return (
        tool_name in write_tools
        or _compact_tool_name(tool_name) in write_tools
        or _looks_like_write_tool(tool_name)
    )


def _append_violation_file(violation: ShadowViolation) -> None:
    root = get_evaluation_root() / "audit"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "shadow-violations.jsonl"
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **violation.to_dict(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
