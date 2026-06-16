"""Build the BN sprint ticket selection shown in the PM inbox."""

from __future__ import annotations

from typing import Any

from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.persistence.db import connect, json_loads
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.pm_inbox.sprint import build_sprint_recommendation
from delivery_runtime.readiness.ticket_scope import load_ticket_scope_for_project, matches_ticket_scope


def build_selected_sprint_payload(*, project_key: str, sprint_number: int | None = None) -> dict[str, Any]:
    """Select LivingColor sprint tickets within configured capacity from ready, estimated work."""
    config = load_delivery_automation_config(project_key=project_key)
    project_key = project_key.strip().upper()
    ticket_scope = load_ticket_scope_for_project(project_key)
    latest_estimations = pm_store.latest_estimations_by_readiness(project_key=project_key)

    if sprint_number is None:
        state = pm_store.get_sprint_state(project_key=project_key)
        memory = (state or {}).get("memory") or {}
        if isinstance(memory, dict):
            try:
                stored_number = int(memory.get("sprintNumber") or 0)
                if stored_number > 0:
                    sprint_number = stored_number
            except (TypeError, ValueError):
                pass

    candidates: list[dict[str, Any]] = []
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM readiness_records
            WHERE project_key = ? AND readiness_status = 'ready'
            ORDER BY updated_at DESC
            """,
            (project_key,),
        ).fetchall()

    for row in rows:
        estimation = latest_estimations.get(row["id"])
        if not estimation:
            continue
        snapshot = json_loads(row["jira_snapshot_json"], {})
        if not isinstance(snapshot, dict):
            snapshot = {}
        if not matches_ticket_scope(snapshot, ticket_scope):
            continue
        candidates.append(
            {
                "readinessId": row["id"],
                "jiraKey": row["jira_key"],
                "title": row["title"],
                "estimatedDays": estimation.get("estimatedDays") or estimation.get("estimated_days") or 1.0,
                "jiraSnapshot": snapshot,
            }
        )

    recommendation = build_sprint_recommendation(
        project_key=project_key,
        candidates=candidates,
        capacity_days=config.sprint.capacity_days,
        duration_days=config.sprint.duration_days,
        sprint_number=sprint_number,
    )

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
                "warnings": ticket.warnings,
            }
            for ticket in recommendation.tickets
        ],
    }


def merge_active_work_orders_into_sprint(
    payload: dict[str, Any],
    *,
    project_key: str,
) -> dict[str, Any]:
    """Keep approved/in-flight tickets visible in the sprint panel."""
    project_key = project_key.strip().upper()
    tickets = [dict(item) for item in (payload.get("tickets") or []) if isinstance(item, dict)]
    existing_by_key = {str(item.get("jiraKey") or ""): item for item in tickets if str(item.get("jiraKey") or "")}

    latest_estimations = pm_store.latest_estimations_by_readiness(project_key=project_key)
    used_days = float(payload.get("usedDays") or 0)

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, jira_key, title, readiness_id, status, current_stage
            FROM work_orders
            WHERE jira_key LIKE ?
              AND status NOT IN ('completed', 'cancelled', 'failed')
            ORDER BY updated_at DESC
            """,
            (f"{project_key}-%",),
        ).fetchall()

    for row in rows:
        jira_key = str(row["jira_key"] or "").strip()
        if not jira_key:
            continue

        work_order_meta = {
            "workOrderId": row["id"],
            "inDevelopment": True,
            "currentStage": row["current_stage"],
            "status": row["status"],
        }

        existing = existing_by_key.get(jira_key)
        if existing:
            existing.update(work_order_meta)
            continue

        estimated_days = 1.0
        readiness_id = str(row["readiness_id"] or "").strip()
        if readiness_id:
            estimation = latest_estimations.get(readiness_id)
            if estimation:
                estimated_days = float(
                    estimation.get("estimatedDays") or estimation.get("estimated_days") or 1.0
                )

        ticket = {
            "readinessId": readiness_id,
            "jiraKey": jira_key,
            "title": row["title"],
            "estimatedDays": estimated_days,
            "priorityRank": len(tickets) + 1,
            "urgencyScore": 0.0,
            "warnings": [],
            **work_order_meta,
        }
        tickets.append(ticket)
        existing_by_key[jira_key] = ticket
        used_days += estimated_days

    merged = dict(payload)
    merged["tickets"] = tickets
    merged["usedDays"] = round(used_days, 2)
    merged["activeDevelopmentCount"] = sum(1 for item in tickets if item.get("inDevelopment"))
    return merged


def persist_selected_sprint(
    *,
    project_key: str,
    payload: dict[str, Any],
    memory_patch: dict[str, Any] | None = None,
) -> None:
    with connect() as conn:
        pm_store.upsert_sprint_state(
            conn,
            project_key=project_key,
            sprint_name=str(payload.get("sprintName") or "LivingColor Sprint"),
            capacity_days=float(payload.get("capacityDays") or 0),
            duration_days=int(payload.get("durationDays") or 14),
            recommendation=payload,
            memory_patch=memory_patch,
        )


def load_selected_sprint_payload(*, project_key: str) -> dict[str, Any]:
    """Return persisted sprint selection when manually overridden, else rebuild."""
    from delivery_runtime.pm_inbox.sprint_reset import maybe_auto_reset_sprint

    project_key = project_key.strip().upper()
    auto_reset = maybe_auto_reset_sprint(project_key=project_key)
    if auto_reset is not None:
        return auto_reset

    state = pm_store.get_sprint_state(project_key=project_key)
    if state and isinstance(state.get("memory"), dict) and state["memory"].get("manualOverride"):
        recommendation = state.get("recommendation") or {}
        if isinstance(recommendation, dict) and recommendation.get("tickets") is not None:
            return merge_active_work_orders_into_sprint(recommendation, project_key=project_key)
    return merge_active_work_orders_into_sprint(
        build_selected_sprint_payload(project_key=project_key),
        project_key=project_key,
    )
