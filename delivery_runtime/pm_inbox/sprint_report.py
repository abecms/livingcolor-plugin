"""Sprint retrospective collection and publishing to Hermes messaging."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from typing import Any, Callable

from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.events.store import EventStore
from delivery_runtime.persistence.db import connect, utc_now_iso
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.work_orders.service import WorkOrderService

logger = logging.getLogger(__name__)


def _today(now: datetime) -> date:
    return now.astimezone(UTC).date()


def _parse_date(raw: Any) -> date | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def sprint_report_dedup_key(*, sprint_number: int, sprint_end_date: str) -> str:
    return f"{sprint_number}:{sprint_end_date}"


def _sprint_memory(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return {}
    memory = state.get("memory") or {}
    return memory if isinstance(memory, dict) else {}


def _sprint_recommendation(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return {}
    recommendation = state.get("recommendation") or {}
    return recommendation if isinstance(recommendation, dict) else {}


def already_published_report(*, memory: dict[str, Any], dedup_key: str) -> bool:
    return str(memory.get("lastSprintReportKey") or "") == dedup_key


def build_sprint_report_snapshot(*, project_key: str) -> dict[str, Any] | None:
    """Collect sprint context for the reporter agent."""
    project_key = project_key.strip().upper()
    config = load_delivery_automation_config(project_key=project_key)
    state = pm_store.get_sprint_state(project_key=project_key)
    memory = _sprint_memory(state)
    recommendation = _sprint_recommendation(state)

    sprint_number = 0
    try:
        sprint_number = max(0, int(memory.get("sprintNumber") or 0))
    except (TypeError, ValueError):
        sprint_number = 0
    if sprint_number <= 0:
        return None

    tickets = [dict(item) for item in (recommendation.get("tickets") or []) if isinstance(item, dict)]
    sprint_keys = {str(item.get("jiraKey") or "").strip().upper() for item in tickets}
    sprint_keys.discard("")

    work_orders = WorkOrderService().list_work_orders()
    sprint_work_orders = [
        {
            "id": item.get("id"),
            "jiraKey": item.get("jiraKey"),
            "title": item.get("title"),
            "status": item.get("status"),
            "currentStage": item.get("currentStage"),
            "updatedAt": item.get("updatedAt"),
        }
        for item in work_orders
        if str(item.get("jiraKey") or "").strip().upper() in sprint_keys
    ]

    status_counts: dict[str, int] = {}
    for item in sprint_work_orders:
        status = str(item.get("status") or "unknown").strip().lower() or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    delivered_keys = {
        str(item.get("jiraKey") or "").strip().upper()
        for item in sprint_work_orders
        if str(item.get("status") or "").strip().lower() == "completed"
    }
    planned_not_delivered = sorted(key for key in sprint_keys if key and key not in delivered_keys)

    latest_run = pm_store.get_latest_daily_run(project_key=project_key)

    return {
        "projectKey": project_key,
        "projectName": config.project_name,
        "communicationLanguage": config.communication_language,
        "sprintNumber": sprint_number,
        "sprint": {
            "number": sprint_number,
            "name": recommendation.get("sprintName") or state.get("sprintName") if state else None,
            "startDate": memory.get("sprintStartDate"),
            "endDate": memory.get("sprintEndDate"),
            "capacityDays": recommendation.get("capacityDays") or state.get("capacityDays") if state else None,
            "usedDays": recommendation.get("usedDays"),
            "durationDays": recommendation.get("durationDays") or state.get("durationDays") if state else None,
            "overflowRisk": recommendation.get("overflowRisk"),
            "warnings": recommendation.get("warnings") or [],
        },
        "ticketsPlanned": [
            {
                "jiraKey": item.get("jiraKey"),
                "title": item.get("title"),
                "estimatedDays": item.get("estimatedDays"),
                "workOrderStatus": next(
                    (
                        wo.get("status")
                        for wo in sprint_work_orders
                        if str(wo.get("jiraKey") or "").upper() == str(item.get("jiraKey") or "").upper()
                    ),
                    None,
                ),
            }
            for item in tickets
        ],
        "workOrders": sprint_work_orders,
        "workOrderStatusCounts": status_counts,
        "deliveredTicketKeys": sorted(delivered_keys),
        "carryOverTicketKeys": planned_not_delivered,
        "latestDailyAnalysis": {
            "runId": latest_run.get("id") if latest_run else None,
            "status": latest_run.get("status") if latest_run else None,
            "completedAt": latest_run.get("completedAt") if latest_run else None,
        },
    }


def _patch_sprint_memory(*, project_key: str, memory_patch: dict[str, Any]) -> None:
    state = pm_store.get_sprint_state(project_key=project_key)
    if not state:
        return
    recommendation = _sprint_recommendation(state)
    with connect() as conn:
        pm_store.upsert_sprint_state(
            conn,
            project_key=project_key,
            sprint_name=str(state.get("sprintName") or recommendation.get("sprintName") or "Sprint"),
            capacity_days=float(state.get("capacityDays") or recommendation.get("capacityDays") or 15),
            duration_days=int(state.get("durationDays") or recommendation.get("durationDays") or 14),
            recommendation=recommendation,
            memory_patch=memory_patch,
        )


def should_run_scheduled_sprint_report(
    *,
    project_key: str,
    now: datetime | None = None,
) -> bool:
    config = load_delivery_automation_config(project_key=project_key)
    if not config.sprint_report_cron.enabled:
        return False

    now = now or datetime.now(UTC)
    if now.hour != config.sprint_report_cron.hour or now.minute != config.sprint_report_cron.minute:
        return False

    state = pm_store.get_sprint_state(project_key=project_key)
    memory = _sprint_memory(state)
    sprint_end = _parse_date(memory.get("sprintEndDate"))
    if sprint_end is None or _today(now) != sprint_end:
        return False

    try:
        sprint_number = max(0, int(memory.get("sprintNumber") or 0))
    except (TypeError, ValueError):
        return False
    if sprint_number <= 0:
        return False

    dedup_key = sprint_report_dedup_key(
        sprint_number=sprint_number,
        sprint_end_date=sprint_end.isoformat(),
    )
    return not already_published_report(memory=memory, dedup_key=dedup_key)


def publish_sprint_report(
    *,
    project_key: str,
    actor: str = "system",
    force: bool = False,
    snapshot: dict[str, Any] | None = None,
    reporter: Callable[[dict[str, Any], str], str] | None = None,
    sender: Callable[[str], dict[str, Any]] | None = None,
    events: EventStore | None = None,
) -> dict[str, Any]:
    """Compose and post a sprint retrospective to the Hermes messaging home channel."""
    project_key = project_key.strip().upper()
    snapshot = snapshot or build_sprint_report_snapshot(project_key=project_key)
    if snapshot is None:
        return {"status": "skipped", "reason": "no_active_sprint"}

    sprint = snapshot.get("sprint") or {}
    sprint_number = int(snapshot.get("sprintNumber") or 0)
    sprint_end_date = str(sprint.get("endDate") or "")
    dedup_key = sprint_report_dedup_key(
        sprint_number=sprint_number,
        sprint_end_date=sprint_end_date,
    )

    state = pm_store.get_sprint_state(project_key=project_key)
    memory = _sprint_memory(state)
    if not force and already_published_report(memory=memory, dedup_key=dedup_key):
        return {"status": "skipped", "reason": "already_published", "dedupKey": dedup_key}

    compose = reporter or _default_compose
    deliver = sender or _default_send

    try:
        message = compose(snapshot, project_key)
    except Exception as exc:
        logger.exception("Sprint reporter agent failed for %s", project_key)
        EventStore().append(
            event_type="SPRINT_REPORT_FAILED",
            actor=actor,
            payload={"projectKey": project_key, "dedupKey": dedup_key, "error": str(exc)},
        )
        return {"status": "failed", "error": str(exc), "dedupKey": dedup_key}

    delivery = deliver(message)
    if not delivery.get("success"):
        error = str(delivery.get("error") or "Messaging delivery failed")
        EventStore().append(
            event_type="SPRINT_REPORT_FAILED",
            actor=actor,
            payload={"projectKey": project_key, "dedupKey": dedup_key, "error": error},
        )
        return {"status": "failed", "error": error, "dedupKey": dedup_key, "messagePreview": message[:240]}

    published_at = utc_now_iso()
    _patch_sprint_memory(
        project_key=project_key,
        memory_patch={
            "lastSprintReportKey": dedup_key,
            "lastSprintReportAt": published_at,
            "lastSprintReportPlatform": delivery.get("platform"),
        },
    )

    store = events or EventStore()
    store.append(
        event_type="SPRINT_REPORT_PUBLISHED",
        actor=actor,
        payload={
            "projectKey": project_key,
            "dedupKey": dedup_key,
            "platform": delivery.get("platform"),
            "sprintNumber": sprint_number,
            "sprintEndDate": sprint_end_date,
        },
    )
    return {
        "status": "sent",
        "dedupKey": dedup_key,
        "platform": delivery.get("platform"),
        "publishedAt": published_at,
        "messagePreview": message[:240],
    }


def maybe_publish_sprint_report_before_reset(
    *,
    project_key: str,
    now: datetime | None = None,
    force: bool = False,
) -> dict[str, Any] | None:
    """Publish the ending sprint report once before the sprint rolls over."""
    project_key = project_key.strip().upper()
    snapshot = build_sprint_report_snapshot(project_key=project_key)
    if snapshot is None:
        return None

    state = pm_store.get_sprint_state(project_key=project_key)
    memory = _sprint_memory(state)
    sprint = snapshot.get("sprint") or {}
    dedup_key = sprint_report_dedup_key(
        sprint_number=int(snapshot.get("sprintNumber") or 0),
        sprint_end_date=str(sprint.get("endDate") or ""),
    )
    if not force and already_published_report(memory=memory, dedup_key=dedup_key):
        return None

    return publish_sprint_report(
        project_key=project_key,
        snapshot=snapshot,
        force=force,
        actor="system",
    )


def _default_compose(snapshot: dict[str, Any], project_key: str) -> str:
    from lc_server.agent_bridge.hermes_sprint_reporter import HermesSprintReporterAgent

    return HermesSprintReporterAgent().compose(snapshot, project_key=project_key)


def _default_send(message: str) -> dict[str, Any]:
    from lc_server.integrations.hermes_messaging import send_to_home_channel

    return send_to_home_channel(message=message)
