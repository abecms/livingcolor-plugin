"""LivingColor PM tools for project-scoped dashboard chat."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from lc_server.context import LOCAL_ORG_ID, ProjectContext, reset_project_context, set_project_context
from lc_server.integrations.project_chat_context import normalize_livingcolor_project_key

logger = logging.getLogger(__name__)


def _serialize_project_settings(project_key: str) -> dict[str, Any]:
    from delivery_runtime.automation.config import load_delivery_automation_config
    from delivery_runtime.readiness.ticket_scope import default_ticket_scope, serialize_ticket_scope

    config = load_delivery_automation_config(project_key=project_key)
    scope = config.ticket_scope or default_ticket_scope()
    return {
        "projectKey": config.project_key,
        "projectName": config.project_name,
        "communicationLanguage": config.communication_language,
        "sprint": {
            "durationDays": config.sprint.duration_days,
            "capacityDays": config.sprint.capacity_days,
            "startWeekday": config.sprint.start_weekday,
        },
        "ticketScope": serialize_ticket_scope(scope),
    }


def _is_livingcolor_pm_chat_context() -> bool:
    import os

    skills = {part.strip() for part in os.environ.get("HERMES_TUI_SKILLS", "").split(",") if part.strip()}
    toolsets = {part.strip() for part in os.environ.get("HERMES_TUI_TOOLSETS", "").split(",") if part.strip()}
    return "livingcolor-pm" in skills or "livingcolor" in toolsets


def resolve_active_livingcolor_project_key(explicit: str | None = None) -> str:
    """Resolve the Jira project key for a PM chat tool call."""
    import os

    for candidate in (
        explicit,
        os.environ.get("HERMES_TUI_LIVINGCOLOR_PROJECT_KEY"),
    ):
        key = normalize_livingcolor_project_key(candidate)
        if key:
            return key

    try:
        from lc_server.context import get_project_context

        ctx = get_project_context()
        if ctx is not None:
            key = ctx.normalized_project_key()
            if key:
                return key
    except Exception:
        pass

    if _is_livingcolor_pm_chat_context():
        raise ValueError(
            "LivingColor project key is missing from the dashboard chat session. "
            "Reopen the project chat panel or reset the workstream."
        )

    from delivery_runtime.automation.config import load_delivery_automation_config

    return load_delivery_automation_config().project_key.strip().upper()


def _ensure_services():
    from agent_surfaces import _ensure_services as ensure

    return ensure()


def _with_project_scope(handler: Callable[..., str]) -> Callable[..., str]:
    def wrapped(args: dict[str, Any], **kwargs: Any) -> str:
        project_key = resolve_active_livingcolor_project_key(args.get("project_key"))
        token = set_project_context(ProjectContext(org_id=LOCAL_ORG_ID, project_key=project_key))
        try:
            return handler(args, project_key=project_key, **kwargs)
        finally:
            reset_project_context(token)

    return wrapped


def tool_get_delivery_context(args: dict[str, Any], *, project_key: str, **_: Any) -> str:
    _ensure_services()
    inbox = _ensure_services().pm_inbox.get_inbox(project_key)
    return json.dumps(
        {
            "success": True,
            "projectKey": project_key,
            "projectSettings": _serialize_project_settings(project_key),
            "selectedSprint": inbox.get("selectedSprint"),
            "recommendedNext": inbox.get("recommendedNext"),
            "executionQueue": inbox.get("executionQueue"),
            "needsClarification": inbox.get("needsClarification") or [],
            "waitingForApproval": inbox.get("waitingForApproval") or [],
            "needsClarificationCount": len(inbox.get("needsClarification") or []),
            "waitingForApprovalCount": len(inbox.get("waitingForApproval") or []),
            "lastRun": inbox.get("lastRun"),
        },
        ensure_ascii=False,
    )


def tool_update_ticket_estimation(args: dict[str, Any], *, project_key: str, **_: Any) -> str:
    _ensure_services()
    jira_key = str(args.get("jira_key") or "").strip().upper()
    if not jira_key:
        return json.dumps({"success": False, "error": "jira_key is required"})
    try:
        result = _ensure_services().pm_inbox.update_ticket_estimation(
            project_key=project_key,
            jira_key=jira_key,
            estimated_days=float(args.get("estimated_days") or 0),
            complexity=args.get("complexity"),
            confidence=args.get("confidence"),
            actor="agent",
        )
        return json.dumps({"success": True, **result}, ensure_ascii=False)
    except Exception as exc:
        logger.exception("livingcolor_update_ticket_estimation failed")
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)


def tool_update_sprint_selection(args: dict[str, Any], *, project_key: str, **_: Any) -> str:
    _ensure_services()
    swap_a = str(args.get("swap_a") or "").strip().upper()
    swap_b = str(args.get("swap_b") or "").strip().upper()
    swap = {"a": swap_a, "b": swap_b} if swap_a and swap_b else None
    try:
        payload = _ensure_services().pm_inbox.update_sprint_selection(
            project_key=project_key,
            tickets=args.get("tickets"),
            exclude=args.get("exclude"),
            swap=swap,
            append=args.get("append"),
            actor="agent",
        )
        return json.dumps({"success": True, "selectedSprint": payload}, ensure_ascii=False)
    except Exception as exc:
        logger.exception("livingcolor_update_sprint_selection failed")
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)


def tool_promote_ticket(args: dict[str, Any], *, project_key: str, **_: Any) -> str:
    _ensure_services()
    from delivery_runtime.pm_inbox import store as pm_store

    jira_key = str(args.get("jira_key") or "").strip().upper()
    if not jira_key:
        return json.dumps({"success": False, "error": "jira_key is required"})

    record = pm_store.get_readiness_record_by_jira_key(project_key=project_key, jira_key=jira_key)
    if not record:
        return json.dumps({"success": False, "error": f"Readiness record not found for {jira_key}"})
    try:
        work_order = _ensure_services().readiness.promote(record["id"], actor="agent")
        return json.dumps(
            {
                "success": True,
                "jiraKey": jira_key,
                "workOrderId": work_order.get("id"),
                "status": work_order.get("status"),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.exception("livingcolor_promote_ticket failed")
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)


def tool_run_daily_analysis(args: dict[str, Any], *, project_key: str, **_: Any) -> str:
    _ensure_services()
    try:
        result = _ensure_services().pm_inbox.run_daily_analysis(project_key)
        return json.dumps({"success": True, **result}, ensure_ascii=False)
    except Exception as exc:
        logger.exception("livingcolor_run_daily_analysis failed")
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)


PM_TOOL_REGISTRATIONS: list[dict[str, Any]] = [
    {
        "name": "livingcolor_get_delivery_context",
        "description": (
            "Load the current LivingColor delivery context for the active Jira project: "
            "project settings (sprint capacity, language, ticket scope), selected sprint, "
            "queue, clarifications, approvals, and last analysis run."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "project_key": {
                    "type": "string",
                    "description": "Jira project key (e.g. BN). Defaults to the dashboard project chat scope.",
                }
            },
        },
        "handler": _with_project_scope(tool_get_delivery_context),
    },
    {
        "name": "livingcolor_update_ticket_estimation",
        "description": "Update the effort estimate for a ready Jira ticket in the active project.",
        "schema": {
            "type": "object",
            "properties": {
                "jira_key": {"type": "string"},
                "estimated_days": {"type": "number"},
                "project_key": {"type": "string"},
                "complexity": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["jira_key", "estimated_days"],
        },
        "handler": _with_project_scope(tool_update_ticket_estimation),
    },
    {
        "name": "livingcolor_update_sprint_selection",
        "description": (
            "Mutate the LivingColor sprint selection: replace ticket list, remove tickets, "
            "swap two tickets, or append tickets."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "tickets": {"type": "array", "items": {"type": "string"}},
                "exclude": {"type": "array", "items": {"type": "string"}},
                "swap_a": {"type": "string"},
                "swap_b": {"type": "string"},
                "append": {"type": "array", "items": {"type": "string"}},
            },
        },
        "handler": _with_project_scope(tool_update_sprint_selection),
    },
    {
        "name": "livingcolor_promote_ticket",
        "description": "Approve a ready ticket for autonomous development (creates a work order).",
        "schema": {
            "type": "object",
            "properties": {
                "jira_key": {"type": "string"},
                "project_key": {"type": "string"},
            },
            "required": ["jira_key"],
        },
        "handler": _with_project_scope(tool_promote_ticket),
    },
    {
        "name": "livingcolor_run_daily_analysis",
        "description": "Run daily Jira scan, qualification, estimation, and sprint rebuild for the project.",
        "schema": {
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
            },
        },
        "handler": _with_project_scope(tool_run_daily_analysis),
    },
]
