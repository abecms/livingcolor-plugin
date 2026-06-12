"""Best-effort Jira comment + status transition after delivery publication."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from lc_server.integrations.jira_delivery_invoker import (
    McpJiraDeliveryInvoker,
    pick_transition_id,
)

from delivery_runtime.shadow.mode import is_shadow_mode

logger = logging.getLogger(__name__)

_DEFAULT_TRANSITION_NAMES = (
    "To Test Internally",
    "Test",
    "A tester",
    "À tester",
    "En test",
    "In Test",
    "Ready for Test",
)

_MAX_TRANSITION_HOPS = 4


class JiraDeliveryInvoker(Protocol):
    def add_comment(self, issue_key: str, body: str) -> dict[str, Any]: ...

    def list_transitions(self, issue_key: str) -> list[dict[str, Any]]: ...

    def transition_issue(self, issue_key: str, *, transition_id: str) -> dict[str, Any]: ...


def resolve_delivery_transition_names(project_key: str | None) -> list[str]:
    from delivery_runtime.readiness.project_mapping import load_project_mapping_entry

    key = str(project_key or "").strip().upper()
    entry = load_project_mapping_entry(key) if key else {}
    configured = entry.get("jira_delivery_transition_names") or entry.get(
        "delivery_completion_transition_names"
    )
    if isinstance(configured, list):
        names = [str(item).strip() for item in configured if str(item).strip()]
        if names:
            return names
    target_status = str(
        entry.get("jira_delivery_target_status")
        or entry.get("delivery_target_status")
        or "Test"
    ).strip()
    return [target_status, *_DEFAULT_TRANSITION_NAMES]


def write_delivery_completion_to_jira(
    issue_key: str,
    comment_body: str,
    *,
    project_key: str | None = None,
    invoker: JiraDeliveryInvoker | None = None,
) -> dict[str, Any]:
    """Post the delivery comment and move the ticket toward the test column."""
    if is_shadow_mode():
        return {"commentPosted": False, "transitionApplied": False, "reason": "shadow_mode"}

    key = str(issue_key or "").strip()
    body = str(comment_body or "").strip()
    if not key:
        return {"commentPosted": False, "transitionApplied": False, "reason": "missing_issue_key"}
    if not body:
        return {"commentPosted": False, "transitionApplied": False, "reason": "missing_comment"}

    client = invoker or McpJiraDeliveryInvoker()
    result: dict[str, Any] = {
        "commentPosted": False,
        "transitionApplied": False,
        "transitionsAttempted": [],
    }

    try:
        client.add_comment(key, body)
        result["commentPosted"] = True
    except Exception as exc:
        logger.warning("Jira delivery comment failed for %s: %s", key, exc)
        result["commentError"] = str(exc)

    preferred_names = resolve_delivery_transition_names(project_key)
    try:
        transition_result = _apply_preferred_transition(client, key, preferred_names)
        result.update(transition_result)
    except Exception as exc:
        logger.warning("Jira delivery transition failed for %s: %s", key, exc)
        result["transitionError"] = str(exc)

    return result


def _apply_preferred_transition(
    client: JiraDeliveryInvoker,
    issue_key: str,
    preferred_names: list[str],
) -> dict[str, Any]:
    attempted: list[dict[str, str]] = []
    for _hop in range(_MAX_TRANSITION_HOPS):
        transitions = client.list_transitions(issue_key)
        transition_id = pick_transition_id(transitions, preferred_names=preferred_names)
        if not transition_id:
            return {
                "transitionApplied": bool(attempted),
                "transitionsAttempted": attempted,
                "availableTransitions": [
                    str(item.get("name") or "") for item in transitions if item.get("name")
                ],
            }
        transition_name = next(
            (
                str(item.get("name") or "")
                for item in transitions
                if str(item.get("id") or "") == transition_id
            ),
            transition_id,
        )
        client.transition_issue(issue_key, transition_id=transition_id)
        attempted.append({"id": transition_id, "name": transition_name})
        if _normalize_transition_name(transition_name) in {
            _normalize_transition_name(name) for name in preferred_names
        }:
            return {
                "transitionApplied": True,
                "transitionsAttempted": attempted,
                "finalTransition": transition_name,
            }
    return {
        "transitionApplied": bool(attempted),
        "transitionsAttempted": attempted,
        "reason": "max_transition_hops_reached",
    }


def _normalize_transition_name(value: str) -> str:
    return " ".join(str(value or "").casefold().split())
