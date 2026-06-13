"""Terminal command policy for hard Scope Contract enforcement (Phase 3F)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from delivery_runtime.development.path_tokens import (
    extract_command_path_arguments,
    is_path_like_command_token,
)
from delivery_runtime.shadow.context import current_delivery_agent_role

PolicyDecision = Literal["allow", "deny", "allow_with_post_check"]


@dataclass(frozen=True)
class CommandPolicyResult:
    decision: PolicyDecision
    reason: str = ""


_INSTALL_PATTERNS = (
    re.compile(r"(?:^|\s)(?:npm\s+install|npm\s+i(?:\s|$)|yarn\s+install|pnpm\s+install|pnpm\s+i(?:\s|$))", re.I),
    re.compile(r"(?:^|\s)composer\s+install\b", re.I),
)

_BUILD_PATTERNS = (
    re.compile(r"(?:^|\s)npm\s+run\s+build\b", re.I),
    re.compile(r"(?:^|\s)yarn\s+build\b", re.I),
    re.compile(r"(?:^|\s)pnpm\s+run\s+build\b", re.I),
)

_TEST_ALLOW_PATTERNS = (
    re.compile(r"(?:^|\s)(?:npm\s+test|npm\s+run\s+test|yarn\s+test|pnpm\s+test|pnpm\s+run\s+test)\b", re.I),
    re.compile(r"(?:^|\s)(?:pytest|phpunit|vendor/bin/phpunit|go\s+test|cargo\s+test)\b", re.I),
)

_GIT_WRITE_PATTERNS = (
    re.compile(r"(?:^|\s)git\s+(?:commit|merge|tag|rebase|cherry-pick)\b", re.I),
)

_GIT_PUSH_PATTERN = re.compile(r"(?:^|\s)git\s+push\b", re.I)

_HTTP_CLI_PATTERNS = (
    re.compile(r"(?:^|\s)curl\b", re.I),
    re.compile(r"(?:^|\s)wget\b", re.I),
    re.compile(r"(?:^|\s)httpie\b", re.I),
)
_INLINE_PYTHON_PATTERN = re.compile(r"(?:^|\s)python3?\s+-c\b", re.I)

_GIT_PUSH_FORCE_FLAGS = frozenset({"-f", "--force", "--force-with-lease", "--force-if-includes"})


def _is_force_push(command: str) -> bool:
    """True when a git push carries a force flag as a standalone token."""
    match = _GIT_PUSH_PATTERN.search(command)
    if not match:
        return False
    for token in command[match.end():].split():
        flag = token.split("=", 1)[0]
        if flag in _GIT_PUSH_FORCE_FLAGS:
            return True
    return False

_SHELL_MUTATION_PATTERNS = (
    re.compile(r"(?:^|\s)rm\b", re.I),
    re.compile(r"(?:^|\s)mv\b", re.I),
    re.compile(r"(?:^|\s)cp\b", re.I),
)


def evaluate_terminal_command(
    command: str,
    *,
    allow_dependency_update: bool = False,
    allow_git_write: bool = False,
    allow_git_push: bool = False,
) -> CommandPolicyResult:
    """Return whether a terminal command may run under hard scope enforcement."""
    normalized = (command or "").strip()
    if not normalized:
        return CommandPolicyResult("allow")

    if _is_force_push(normalized):
        return CommandPolicyResult("deny", "force push is never allowed.")

    if current_delivery_agent_role() == "publisher":
        if any(pattern.search(normalized) for pattern in _HTTP_CLI_PATTERNS):
            return CommandPolicyResult(
                "deny",
                "HTTP CLI tools (curl/wget/httpie) are forbidden for the publisher; use GitLab MCP tools.",
            )
        if _INLINE_PYTHON_PATTERN.search(normalized):
            return CommandPolicyResult(
                "deny",
                "Inline python is forbidden for the publisher; use GitLab MCP tools.",
            )

    if (
        not allow_git_push
        and not allow_git_write
        and _GIT_PUSH_PATTERN.search(normalized)
    ):
        return CommandPolicyResult(
            "deny",
            "git push is forbidden outside the mr_publication phase.",
        )

    if not allow_git_write and any(pattern.search(normalized) for pattern in _GIT_WRITE_PATTERNS):
        return CommandPolicyResult(
            "deny",
            "git write operations (commit/merge/tag/rebase) are forbidden during delivery development.",
        )

    if not allow_dependency_update and any(pattern.search(normalized) for pattern in _INSTALL_PATTERNS):
        return CommandPolicyResult(
            "deny",
            "Dependency installs are forbidden unless allowDependencyUpdate=true on the Scope Contract.",
        )

    if any(pattern.search(normalized) for pattern in _BUILD_PATTERNS):
        return CommandPolicyResult(
            "allow_with_post_check",
            "Build commands are allowed but generated artifacts in forbidden paths will be rolled back.",
        )

    if any(pattern.search(normalized) for pattern in _TEST_ALLOW_PATTERNS):
        return CommandPolicyResult("allow")

    if any(pattern.search(normalized) for pattern in _SHELL_MUTATION_PATTERNS):
        return CommandPolicyResult(
            "allow_with_post_check",
            "Shell file mutations require post-command scope verification.",
        )

    return CommandPolicyResult("allow")


def extract_command_paths(command: str) -> list[str]:
    """Best-effort extraction of path-like tokens from a shell command."""
    return extract_command_path_arguments(command)


__all__ = [
    "CommandPolicyResult",
    "PolicyDecision",
    "evaluate_terminal_command",
    "extract_command_paths",
    "is_path_like_command_token",
]
