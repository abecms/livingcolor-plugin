"""Shared shell path token helpers for delivery guards."""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

_PATH_EXTENSIONS = (
    ".json",
    ".js",
    ".ts",
    ".tsx",
    ".css",
    ".md",
    ".php",
    ".py",
    ".yaml",
    ".yml",
    ".patch",
)

_PATH_ARGUMENT_VERBS = frozenset(
    {
        "cd",
        "cp",
        "mv",
        "rm",
        "cat",
        "ls",
        "tee",
        "touch",
        "mkdir",
        "head",
        "tail",
        "chmod",
        "chown",
        "sed",
    }
)

_GLOB_ONLY_TOKENS = frozenset({".", "..", "./", "../*", "*", "**", "/*", "/**"})

# Shell redirection targets — not repo paths; blocking these breaks normal commands.
_SHELL_DEVICE_PATHS = frozenset(
    {
        "/dev/null",
        "/dev/zero",
        "/dev/tty",
        "/dev/stdin",
        "/dev/stdout",
        "/dev/stderr",
        "/dev/urandom",
    }
)


def is_shell_device_path(path: str) -> bool:
    """Return True for pseudo-paths used in redirects (e.g. 2>/dev/null)."""
    cleaned = (path or "").strip().strip("'\"")
    if not cleaned:
        return False
    normalized = cleaned.replace("\\", "/")
    if normalized in _SHELL_DEVICE_PATHS:
        return True
    if re.fullmatch(r"/dev/fd/\d+", normalized):
        return True
    return False


def is_shell_redirect_fragment(path: str) -> bool:
    """True for unparsed redirect syntax (e.g. 2>/dev/null) mistaken as paths."""
    cleaned = (path or "").strip().strip("'\"")
    if not cleaned:
        return False
    return bool(re.fullmatch(r"&?>?&?\d*>>?[^\s&|;]+", cleaned))


def should_ignore_path_token(path: str) -> bool:
    """Return True when a token is not a real filesystem target worth inspecting."""
    cleaned = (path or "").strip().strip("'\"")
    if not cleaned:
        return True
    if cleaned in _GLOB_ONLY_TOKENS:
        return True
    if is_glob_only_token(cleaned):
        return True
    if is_shell_device_path(cleaned):
        return True
    if is_shell_redirect_fragment(cleaned):
        return True
    return False


def is_glob_only_token(token: str) -> bool:
    cleaned = token.strip("'\"")
    if not cleaned:
        return True
    if cleaned in _GLOB_ONLY_TOKENS:
        return True
    if "*" in cleaned or "?" in cleaned:
        return True
    return False


def is_path_like_command_token(token: str) -> bool:
    """Return True when a shell token looks like a filesystem path argument."""
    cleaned = token.strip("'\"")
    if should_ignore_path_token(cleaned):
        return False
    if cleaned.startswith("-") or "://" in cleaned:
        return False
    if cleaned.startswith("/") or cleaned.startswith("./") or cleaned.startswith("../"):
        return True
    if "/" in cleaned:
        return True
    if cleaned.endswith(_PATH_EXTENSIONS):
        return True
    return False


def is_hard_blocked_path(path: str) -> bool:
    """Return True for known escape targets that must never be accessed."""
    cleaned = (path or "").strip()
    if not cleaned:
        return False
    expanded = str(Path(cleaned).expanduser())
    normalized = expanded.replace("\\", "/")
    lowered = normalized.lower()
    if "/side-projects/agent-lc" in lowered or lowered.endswith("/agent-lc"):
        return True
    if "/etc/passwd" in lowered or lowered == "/etc/passwd":
        return True
    if "/.ssh" in lowered or lowered.endswith("/.ssh"):
        return True
    if re.search(r"(?:^|/)\.\.(?:/|$)", normalized):
        segments = [part for part in normalized.split("/") if part and part != "."]
        depth = 0
        for part in segments:
            if part == "..":
                depth += 1
            else:
                depth = max(depth - 1, 0)
        if depth >= 2:
            return True
    return False


def extract_command_path_arguments(command: str) -> list[str]:
    """Extract filesystem path arguments from commands that actually touch paths."""
    normalized = (command or "").strip()
    if not normalized:
        return []

    paths: list[str] = []
    for match in re.finditer(r"(?:^|[\s])(\d*)>>\s*([^\s&|;]+)", normalized):
        paths.append(match.group(2).strip("'\" "))
    for match in re.finditer(r"(?:^|[\s])(\d*)>\s*([^\s&|;]+)", normalized):
        candidate = match.group(2).strip("'\" ")
        if candidate not in {"|", ">&"}:
            paths.append(candidate)
    for match in re.finditer(r"(?:^|[\s])&>\s*([^\s&|;]+)", normalized):
        paths.append(match.group(1).strip("'\" "))
    for match in re.finditer(r"(?:^|[\s])>\s*&\s*([^\s&|;]+)", normalized):
        paths.append(match.group(1).strip("'\" "))

    try:
        tokens = shlex.split(normalized)
    except ValueError:
        tokens = normalized.split()

    index = 0
    while index < len(tokens):
        verb = tokens[index].strip("'\"")
        if verb not in _PATH_ARGUMENT_VERBS:
            index += 1
            continue

        index += 1
        if verb == "sed":
            index = _consume_sed_path_arguments(tokens, index, paths)
            continue

        while index < len(tokens):
            arg = tokens[index].strip("'\"")
            if arg in {"&&", "||", ";", "|"}:
                break
            if arg in _PATH_ARGUMENT_VERBS:
                break
            if arg.startswith("-"):
                index += 1
                continue
            if is_path_like_command_token(arg):
                paths.append(arg)
            index += 1

    deduped: list[str] = []
    seen: set[str] = set()
    for item in paths:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def hermes_skills_roots() -> list[Path]:
    """Roots where Hermes/LivingColor skill files may be loaded read-only."""
    from hermes_constants import get_bundled_skills_dir

    hermes_home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser().resolve()
    roots = [hermes_home / "skills"]
    try:
        from lc_constants import get_livingcolor_home

        roots.append(get_livingcolor_home().resolve() / "skills")
    except Exception:
        pass
    plugin_root = Path(__file__).resolve().parents[2]
    bundled = get_bundled_skills_dir(plugin_root / "skills")
    if bundled.is_dir():
        roots.append(bundled.resolve())
    return roots


def is_allowed_readonly_skill_path(path: str) -> bool:
    """Return True when a path points at a bundled Hermes skill (read-only access)."""
    cleaned = (path or "").strip().strip("'\"")
    if not cleaned or should_ignore_path_token(cleaned):
        return False
    try:
        absolute = Path(cleaned).expanduser().resolve()
    except OSError:
        return False
    for root in hermes_skills_roots():
        try:
            absolute.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


_TERMINAL_WRITE_VERBS = frozenset({"cp", "mv", "rm", "tee", "touch", "chmod", "chown"})


def terminal_path_access(command: str, path_token: str) -> str:
    """Return 'read' or 'write' for a shell path token under workspace confinement."""
    if not is_allowed_readonly_skill_path(path_token):
        return "write"
    normalized = (command or "").strip()
    if re.search(r"\bsed\b[^;\n|&]*\s+-i", normalized):
        return "write"
    try:
        tokens = shlex.split(normalized)
    except ValueError:
        tokens = normalized.split()
    for token in tokens:
        if token.strip("'\"") in _TERMINAL_WRITE_VERBS:
            return "write"
    return "read"


def is_allowed_work_order_artifact_path(absolute: Path, workspace_root: Path) -> bool:
    """Allow sibling artifact files under the current work order root only."""
    artifact_root = workspace_root.resolve().parent
    try:
        relative = absolute.resolve().relative_to(artifact_root)
    except ValueError:
        return False
    if not relative.parts:
        return False
    head = relative.parts[0]
    if head == "workspace":
        return False
    if head == "patches":
        return True
    if len(relative.parts) == 1:
        return relative.suffix in {".json", ".md", ".patch"}
    return False


def _consume_sed_path_arguments(tokens: list[str], index: int, paths: list[str]) -> int:
    while index < len(tokens):
        arg = tokens[index].strip("'\"")
        if arg in {"&&", "||", ";", "|"}:
            return index
        if arg in _PATH_ARGUMENT_VERBS:
            return index
        if arg.startswith("-"):
            if arg in {"-i", "-I"}:
                backup = arg[2:]
                if backup:
                    index += 1
                    continue
            index += 1
            continue
        if is_path_like_command_token(arg):
            paths.append(arg)
        index += 1
    return index
