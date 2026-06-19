"""Helpers for limiting delivery analysis to Jira To Do work."""

from __future__ import annotations

import unicodedata
from typing import Any

_TODO_STATUS_TOKENS = ("to do", "todo", "à faire", "a faire", "open", "backlog", "new")
_REOPENED_STATUS_TOKENS = (
    "reopened",
    "rouvert",
    "rouverte",
    "reouvert",
    "reouverte",
    "re opened",
    "re open",
    "re ouvert",
    "re ouverte",
)
_NON_TODO_CATEGORIES = {"in progress", "done", "indeterminate", "complete", "closed"}

# Common Jira workflow status names for reopened work (project-specific names are still matched in Python).
REOPENED_JIRA_STATUS_NAMES = (
    "Reopened",
    "Rouvert",
    "Rouverte",
    "ROUVERT",
    "ROUVERTE",
    "Re-opened",
    "Re-ouvert",
    "Réouvert",
    "Ré-ouvert",
    "REOPENED",
)

# Explicit To Do status names when statusCategory is missing or localized.
TODO_JIRA_STATUS_NAMES = (
    "To Do",
    "Todo",
    "Open",
    "Backlog",
    "New",
    "À faire",
    "A faire",
    "À FAIRE",
    "A FAIRE",
)


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _normalize_status_key(value: str) -> str:
    text = _strip_accents(value.strip().lower())
    return " ".join(text.replace("_", " ").replace("-", " ").split())


def is_reopened_ticket(snapshot: dict[str, Any]) -> bool:
    """Return True when a ticket was explicitly reopened in the Jira workflow."""
    status = _normalize_status_key(str(snapshot.get("status") or ""))
    if not status:
        return False
    return any(token in status for token in _REOPENED_STATUS_TOKENS)


def is_todo_ticket(snapshot: dict[str, Any]) -> bool:
    """Return True when a ticket is in Jira To Do / À faire scope for daily analysis."""
    if is_reopened_ticket(snapshot):
        return True

    category = _normalize_status_key(str(snapshot.get("statusCategory") or ""))
    if category:
        if category in _NON_TODO_CATEGORIES:
            return False
        if category in {"to do", "new"}:
            return True

    status = _normalize_status_key(str(snapshot.get("status") or ""))
    if not status:
        return False

    return any(token in status for token in _TODO_STATUS_TOKENS)
