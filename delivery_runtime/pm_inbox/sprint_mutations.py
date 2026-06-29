"""Manual sprint selection mutations for PM chat and Mission Control."""

from __future__ import annotations

from typing import Any

from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.persistence.db import connect, json_loads
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.pm_inbox.sprint import build_sprint_recommendation
from delivery_runtime.pm_inbox.sprint_selection import load_selected_sprint_payload, persist_selected_sprint
def _load_ready_ticket(
    *,
    project_key: str,
    jira_key: str,
) -> dict[str, Any] | None:
    key = jira_key.strip().upper()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM readiness_records
            WHERE project_key = ? AND jira_key = ? AND readiness_status = 'ready'
            """,
            (project_key, key),
        ).fetchone()
    if not row:
        return None
    snapshot = json_loads(row["jira_snapshot_json"], {})
    if not isinstance(snapshot, dict):
        snapshot = {}
    estimations = pm_store.latest_estimations_by_readiness(project_key=project_key)
    estimation = estimations.get(row["id"])
    if not estimation:
        return None
    return {
        "readinessId": row["id"],
        "jiraKey": row["jira_key"],
        "title": row["title"],
        "estimatedDays": estimation.get("estimatedDays") or estimation.get("estimated_days") or 1.0,
        "jiraSnapshot": snapshot,
    }


def _payload_from_recommendation(recommendation) -> dict[str, Any]:
    return {
        "sprintName": recommendation.sprint_name,
        "capacityDays": recommendation.capacity_days,
        "usedDays": recommendation.used_days,
        "durationDays": recommendation.duration_days,
        "overflowRisk": recommendation.overflow_risk,
        "warnings": recommendation.warnings,
        "tickets": [
            {
                "readinessId": ticket.readiness_id,
                "jiraKey": ticket.jira_key,
                "title": ticket.title,
                "estimatedDays": ticket.estimated_days,
                "priorityRank": ticket.priority_rank,
                "urgencyScore": ticket.urgency_score,
                "sprintSelected": True,
                "warnings": ticket.warnings,
            }
            for ticket in recommendation.tickets
        ],
    }


def _current_ticket_keys(project_key: str) -> list[str]:
    payload = load_selected_sprint_payload(project_key=project_key)
    return [str(item["jiraKey"]) for item in payload.get("tickets", [])]


def _build_payload_from_keys(
    *,
    project_key: str,
    ticket_keys: list[str],
) -> dict[str, Any]:
    config = load_delivery_automation_config(project_key=project_key)
    candidates: list[dict[str, Any]] = []
    missing: list[str] = []
    for jira_key in ticket_keys:
        ticket = _load_ready_ticket(project_key=project_key, jira_key=jira_key)
        if not ticket:
            missing.append(jira_key)
            continue
        candidates.append(ticket)
    if missing:
        raise ValueError(f"Tickets are not ready with estimates: {', '.join(missing)}")

    ranked = build_sprint_recommendation(
        project_key=project_key,
        candidates=candidates,
        capacity_days=config.sprint.capacity_days,
        duration_days=config.sprint.duration_days,
    )
    by_key = {ticket.jira_key: ticket for ticket in ranked.tickets}
    selected = []
    used = 0.0
    warnings: list[str] = []
    overflow = False
    for jira_key in ticket_keys:
        ticket = by_key.get(jira_key)
        if ticket is None:
            raise ValueError(f"Ticket {jira_key} could not be placed in sprint")
        selected.append(ticket)
        used += ticket.estimated_days
        if used > ranked.capacity_days + 0.01:
            overflow = True

    if overflow:
        warnings.append("Manual sprint selection exceeds configured capacity")

    manual = type(ranked)(
        sprint_name=ranked.sprint_name,
        capacity_days=ranked.capacity_days,
        used_days=round(used, 2),
        duration_days=ranked.duration_days,
        tickets=selected,
        warnings=sorted(set(warnings)),
        overflow_risk=overflow,
    )
    return _payload_from_recommendation(manual)


def persist_manual_sprint(*, project_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    from delivery_runtime.persistence.db import utc_now_iso

    project_key = project_key.strip().upper()
    persist_selected_sprint(
        project_key=project_key,
        payload=payload,
        memory_patch={
            "manualOverride": True,
            "manualOverrideAt": utc_now_iso(),
            "emptyBacklogUntilAnalysis": False,
        },
    )
    return payload


def update_sprint_selection(
    *,
    project_key: str,
    tickets: list[str] | None = None,
    exclude: list[str] | None = None,
    swap: dict[str, str] | None = None,
    append: list[str] | None = None,
) -> dict[str, Any]:
    project_key = project_key.strip().upper()
    current = _current_ticket_keys(project_key)

    if tickets is not None:
        normalized = [item.strip().upper() for item in tickets if str(item).strip()]
        payload = _build_payload_from_keys(project_key=project_key, ticket_keys=normalized)
        return persist_manual_sprint(project_key=project_key, payload=payload)

    working = list(current)

    if swap:
        left = str(swap.get("a") or swap.get("from") or "").strip().upper()
        right = str(swap.get("b") or swap.get("to") or "").strip().upper()
        if not left or not right:
            raise ValueError("swap requires two jira keys")
        if left not in working and right not in working:
            raise ValueError("neither ticket is in the current sprint")
        if left in working and right in working:
            left_index = working.index(left)
            right_index = working.index(right)
            working[left_index], working[right_index] = working[right_index], working[left_index]
        elif left in working:
            working[working.index(left)] = right
        else:
            working[working.index(right)] = left

    if exclude:
        excluded = {item.strip().upper() for item in exclude if str(item).strip()}
        working = [key for key in working if key not in excluded]

    if append:
        for item in append:
            key = str(item).strip().upper()
            if key and key not in working:
                working.append(key)

    if not working and not (exclude or append or swap):
        raise ValueError("No sprint mutation parameters provided")

    payload = _build_payload_from_keys(project_key=project_key, ticket_keys=working)
    return persist_manual_sprint(project_key=project_key, payload=payload)
