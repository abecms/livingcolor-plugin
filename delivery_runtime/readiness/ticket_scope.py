"""Configurable Jira ticket scope for analysis and automation."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

from delivery_runtime.readiness.todo_filter import is_todo_ticket

_STATUS_GROUP_TODO = "todo"
_STATUS_GROUP_IN_PROGRESS = "in_progress"

_IN_PROGRESS_CATEGORIES = {"in progress", "indeterminate"}
_IN_PROGRESS_STATUS_TOKENS = (
    "in progress",
    "en cours",
    "doing",
    "review",
    "in review",
    "code review",
)


def _normalize_token(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _normalize_assignee(value: str) -> str:
    return _strip_accents(_normalize_token(value))


def _assignee_aliases(snapshot: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for field in ("assignee", "assigneeDisplayName", "assigneeEmail"):
        raw = str(snapshot.get(field) or "").strip()
        if not raw or raw.lower() == "unassigned":
            continue
        aliases.add(_normalize_assignee(raw))
        if "@" in raw:
            local_part = raw.split("@", 1)[0]
            aliases.add(_normalize_assignee(local_part.replace(".", " ")))
            aliases.add(_normalize_assignee(local_part))
    return {alias for alias in aliases if alias}


def _assignee_target_aliases(name: str) -> set[str]:
    aliases: set[str] = set()
    raw = str(name).strip()
    if not raw:
        return aliases
    aliases.add(_normalize_assignee(raw))
    if "@" in raw:
        local_part = raw.split("@", 1)[0]
        aliases.add(_normalize_assignee(local_part.replace(".", " ")))
        aliases.add(_normalize_assignee(local_part))
    return {alias for alias in aliases if alias}


def _assignee_tokens_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if left in right or right in left:
        return True
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if len(left_tokens) >= 2 and left_tokens <= right_tokens:
        return True
    if len(right_tokens) >= 2 and right_tokens <= left_tokens:
        return True
    return False


def _assignee_matches_target(snapshot_aliases: set[str], target: str) -> bool:
    target_aliases = _assignee_target_aliases(target)
    for snapshot_alias in snapshot_aliases:
        for target_alias in target_aliases:
            if _assignee_tokens_match(snapshot_alias, target_alias):
                return True
    return False


@dataclass(frozen=True)
class TicketScopeConfig:
    status_groups: tuple[str, ...] = (_STATUS_GROUP_TODO,)
    assignees: tuple[str, ...] = ()
    include_unassigned: bool = True
    match_mode: str = "all"


def default_ticket_scope() -> TicketScopeConfig:
    return TicketScopeConfig(status_groups=(_STATUS_GROUP_TODO,))


def parse_ticket_scope(raw: Any) -> TicketScopeConfig:
    if not isinstance(raw, dict):
        return default_ticket_scope()

    groups_raw = raw.get("statusGroups") or raw.get("status_groups") or []
    groups: list[str] = []
    if isinstance(groups_raw, list):
        for item in groups_raw:
            token = _normalize_status_group(str(item))
            if token:
                groups.append(token)
    if not groups:
        groups = [_STATUS_GROUP_TODO]

    assignees_raw = raw.get("assignees") or []
    assignees: list[str] = []
    if isinstance(assignees_raw, list):
        for item in assignees_raw:
            text = str(item).strip()
            if text:
                assignees.append(text)

    include_unassigned = raw.get("includeUnassigned")
    if include_unassigned is None:
        include_unassigned = raw.get("include_unassigned")
    if include_unassigned is None:
        include_unassigned = not bool(assignees)
    else:
        include_unassigned = bool(include_unassigned)

    match_mode = _normalize_token(str(raw.get("matchMode") or raw.get("match_mode") or "all"))
    if match_mode not in {"all", "any"}:
        match_mode = "all"

    return TicketScopeConfig(
        status_groups=tuple(groups),
        assignees=tuple(assignees),
        include_unassigned=include_unassigned,
        match_mode=match_mode,
    )


def serialize_ticket_scope(scope: TicketScopeConfig) -> dict[str, Any]:
    return {
        "statusGroups": list(scope.status_groups),
        "assignees": list(scope.assignees),
        "includeUnassigned": scope.include_unassigned,
        "matchMode": scope.match_mode,
    }


def matches_in_progress_ticket(snapshot: dict[str, Any]) -> bool:
    category = _normalize_token(str(snapshot.get("statusCategory") or ""))
    if category in _IN_PROGRESS_CATEGORIES:
        return True
    status = _normalize_token(str(snapshot.get("status") or ""))
    if not status:
        return False
    return any(token in status for token in _IN_PROGRESS_STATUS_TOKENS)


def _normalize_status_group(group: str) -> str:
    normalized = _normalize_token(group).replace(" ", "_")
    if normalized in {_STATUS_GROUP_TODO, _STATUS_GROUP_IN_PROGRESS}:
        return normalized
    return ""


def matches_status_group(snapshot: dict[str, Any], group: str) -> bool:
    normalized = _normalize_status_group(group)
    if normalized == _STATUS_GROUP_TODO:
        return is_todo_ticket(snapshot)
    if normalized == _STATUS_GROUP_IN_PROGRESS:
        return matches_in_progress_ticket(snapshot)
    return False


def matches_assignee_filter(snapshot: dict[str, Any], scope: TicketScopeConfig) -> bool:
    if not scope.assignees:
        return True

    snapshot_aliases = _assignee_aliases(snapshot)
    if not snapshot_aliases:
        return scope.include_unassigned

    return any(_assignee_matches_target(snapshot_aliases, name) for name in scope.assignees if str(name).strip())


def matches_ticket_scope(snapshot: dict[str, Any], scope: TicketScopeConfig | None = None) -> bool:
    resolved = scope or default_ticket_scope()
    status_active = bool(resolved.status_groups)
    assignee_active = bool(resolved.assignees)

    if not status_active and not assignee_active:
        return is_todo_ticket(snapshot)

    status_ok = True
    if status_active:
        status_ok = any(matches_status_group(snapshot, group) for group in resolved.status_groups)

    assignee_ok = True
    if assignee_active:
        assignee_ok = matches_assignee_filter(snapshot, resolved)

    if not status_active or not assignee_active:
        return status_ok and assignee_ok

    if resolved.match_mode == "any":
        return status_ok or assignee_ok
    return status_ok and assignee_ok


def _escape_jql_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _todo_status_jql_clause() -> str:
    from delivery_runtime.readiness.todo_filter import REOPENED_JIRA_STATUS_NAMES

    reopened = ", ".join(f'"{_escape_jql_string(name)}"' for name in REOPENED_JIRA_STATUS_NAMES)
    return f'(statusCategory = "To Do" OR status in ({reopened}))'


def _status_jql_clause(scope: TicketScopeConfig) -> str | None:
    parts: list[str] = []
    if _STATUS_GROUP_TODO in scope.status_groups:
        parts.append(_todo_status_jql_clause())
    if _STATUS_GROUP_IN_PROGRESS in scope.status_groups:
        parts.append('statusCategory = "In Progress"')
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return f"({' OR '.join(parts)})"


def _assignee_jql_clause(scope: TicketScopeConfig) -> str | None:
    names = [
        f'"{_escape_jql_string(name)}"'
        for name in scope.assignees
        if str(name).strip()
    ]
    if not names:
        return None
    joined = ", ".join(names)
    if scope.include_unassigned:
        return f"(assignee in ({joined}) OR assignee is EMPTY)"
    return f"assignee in ({joined})"


def build_ticket_scope_jql_variants(
    project_key: str,
    scope: TicketScopeConfig | None = None,
) -> tuple[str, ...]:
    """Build Jira JQL queries that match the configured ticket scope."""
    from hermes_cli.jira_dashboard import _ISSUE_VISIBILITY_FILTER

    resolved = scope or default_ticket_scope()
    safe_key = _escape_jql_string(project_key.strip().upper())
    base = f'project = "{safe_key}" AND {_ISSUE_VISIBILITY_FILTER}'

    status_clause = _status_jql_clause(resolved)
    assignee_clause = _assignee_jql_clause(resolved)

    if status_clause and assignee_clause:
        if resolved.match_mode == "any":
            filter_clause = f"({status_clause} OR {assignee_clause})"
        else:
            filter_clause = f"{status_clause} AND {assignee_clause}"
    elif status_clause:
        filter_clause = status_clause
    elif assignee_clause:
        filter_clause = assignee_clause
    else:
        filter_clause = _todo_status_jql_clause()

    return (
        f"{base} AND {filter_clause} ORDER BY updated DESC",
        f"{base} AND {filter_clause} ORDER BY created DESC",
    )


def needs_broad_jira_fetch(scope: TicketScopeConfig | None = None) -> bool:
    """Use a broad Jira fetch when Python-side filtering is required for accuracy."""
    resolved = scope or default_ticket_scope()
    if resolved.assignees:
        return True
    groups = set(resolved.status_groups)
    if not groups:
        return True
    # Reopened status names vary per Jira workflow — always post-filter in Python for todo scope.
    if _STATUS_GROUP_TODO in groups:
        return True
    return bool(groups - {_STATUS_GROUP_TODO})


def load_ticket_scope_for_project(project_key: str) -> TicketScopeConfig:
    key = project_key.strip().upper()
    if not key:
        return default_ticket_scope()

    from delivery_runtime.readiness.project_mapping import load_project_mapping

    mapping = load_project_mapping()
    if isinstance(mapping, dict):
        block = mapping.get(key) or mapping.get(key.lower()) or {}
        if isinstance(block, dict) and block.get("ticket_scope") is not None:
            return parse_ticket_scope(block.get("ticket_scope"))

    from delivery_runtime.automation.config import (
        _load_yaml_mapping,
        _resolve_active_project_key,
        delivery_config_path,
    )

    delivery_path = delivery_config_path()
    if delivery_path.exists():
        merged = _load_yaml_mapping(delivery_path)
        if _resolve_active_project_key(merged, None) == key:
            legacy = merged.get("ticket_scope") or merged.get("ticketScope")
            if legacy is not None:
                return parse_ticket_scope(legacy)

    return default_ticket_scope()


def persist_ticket_scope_for_project(project_key: str, scope: TicketScopeConfig) -> None:
    key = project_key.strip().upper()
    if not key:
        raise ValueError("project_key is required")

    from delivery_runtime.readiness.project_mapping import load_project_mapping

    mapping = load_project_mapping()
    if not isinstance(mapping, dict):
        mapping = {}
    block = mapping.get(key) or mapping.get(key.lower()) or {}
    entry = block if isinstance(block, dict) else {}
    entry["ticket_scope"] = serialize_ticket_scope(scope)
    mapping[key] = entry

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to save ticket scope") from exc

    from delivery_runtime.persistence.paths import get_project_mapping_path

    path = get_project_mapping_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(mapping, sort_keys=False, allow_unicode=True), encoding="utf-8")
