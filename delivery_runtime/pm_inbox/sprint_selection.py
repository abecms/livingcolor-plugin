"""Build the BN sprint ticket selection shown in the PM inbox."""

from __future__ import annotations

from typing import Any

from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.persistence.db import connect, json_loads
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.pm_inbox.sprint import PRIORITY_RANK, _priority_rank, build_sprint_recommendation
from delivery_runtime.readiness.ticket_scope import load_ticket_scope_for_project, matches_ticket_scope

_SPRINT_BACKLOG_STATUSES = ("ready", "needs_clarification", "not_ready", "analysis_failed")
_ANALYSIS_FAILED_WARNING = "Latest LLM analysis failed; review the error before promotion"


def _latest_analysis_error(row_or_item: Any) -> str:
    if isinstance(row_or_item, dict):
        value = row_or_item.get("lastAnalysisError") or row_or_item.get("last_analysis_error")
    else:
        value = row_or_item["last_analysis_error"]
    return str(value or "").strip()


def _append_latest_analysis_warning(warnings: list[str], row_or_item: Any) -> list[str]:
    if _latest_analysis_error(row_or_item) and _ANALYSIS_FAILED_WARNING not in warnings:
        warnings.append(_ANALYSIS_FAILED_WARNING)
    return warnings


def _latest_analysis_failure_metadata(project_key: str) -> dict[str, dict[str, str | None]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT jira_key, last_analysis_error, last_analysis_failed_at
            FROM readiness_records
            WHERE project_key = ? AND readiness_status NOT IN ('promoted', 'dismissed')
            """,
            (project_key,),
        ).fetchall()
    return {
        str(row["jira_key"]): {
            "lastAnalysisError": row["last_analysis_error"],
            "lastAnalysisFailedAt": row["last_analysis_failed_at"],
        }
        for row in rows
    }


def _merge_latest_analysis_failure_warnings(payload: dict[str, Any], *, project_key: str) -> dict[str, Any]:
    failure_metadata = _latest_analysis_failure_metadata(project_key)
    if not failure_metadata:
        return payload

    merged = dict(payload)
    tickets: list[dict[str, Any]] = []
    for ticket in payload.get("tickets") or []:
        if not isinstance(ticket, dict):
            continue
        enriched = dict(ticket)
        metadata = failure_metadata.get(str(enriched.get("jiraKey") or ""))
        if metadata:
            enriched.update(metadata)
            warnings = list(enriched.get("warnings") or [])
            if _latest_analysis_error(enriched):
                _append_latest_analysis_warning(warnings, enriched)
            elif enriched.get("readinessStatus") != "analysis_failed":
                warnings = [warning for warning in warnings if warning != _ANALYSIS_FAILED_WARNING]
            enriched["warnings"] = warnings
        tickets.append(enriched)
    merged["tickets"] = tickets
    return merged


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
    status_placeholders = ", ".join("?" for _ in _SPRINT_BACKLOG_STATUSES)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM readiness_records
            WHERE project_key = ? AND readiness_status IN ({status_placeholders})
            ORDER BY updated_at DESC
            """,
            (project_key, *_SPRINT_BACKLOG_STATUSES),
        ).fetchall()

    for row in rows:
        estimation = latest_estimations.get(row["id"])
        snapshot = json_loads(row["jira_snapshot_json"], {})
        if not isinstance(snapshot, dict):
            snapshot = {}
        if not matches_ticket_scope(snapshot, ticket_scope):
            continue

        status = str(row["readiness_status"] or "")
        estimated_days = None
        if status != "needs_clarification":
            if estimation:
                estimated_days = estimation.get("estimatedDays") or estimation.get("estimated_days")
            if estimated_days is None and row["estimated_days"] is not None:
                estimated_days = float(row["estimated_days"])
        if estimated_days is None and status == "analysis_failed":
            estimated_days = 0.0
        if estimated_days is None and status != "needs_clarification":
            continue

        candidates.append(
            {
                "readinessId": row["id"],
                "jiraKey": row["jira_key"],
                "title": row["title"],
                "estimatedDays": float(estimated_days) if estimated_days is not None else None,
                "readinessStatus": status,
                "lastAnalysisError": row["last_analysis_error"],
                "lastAnalysisFailedAt": row["last_analysis_failed_at"],
                "jiraSnapshot": snapshot,
            }
        )

    ready_candidates = [item for item in candidates if item.get("readinessStatus") == "ready"]
    recommendation = build_sprint_recommendation(
        project_key=project_key,
        candidates=ready_candidates,
        capacity_days=config.sprint.capacity_days,
        duration_days=config.sprint.duration_days,
        sprint_number=sprint_number,
    )

    selected_ready_keys = {ticket.jira_key for ticket in recommendation.tickets}
    ready_candidates_by_id = {str(item["readinessId"]): item for item in ready_candidates}
    tickets_payload: list[dict[str, Any]] = [
        {
            "readinessId": ticket.readiness_id,
            "jiraKey": ticket.jira_key,
            "title": ticket.title,
            "estimatedDays": ticket.estimated_days,
            "priorityRank": ticket.priority_rank,
            "urgencyScore": ticket.urgency_score,
            "warnings": _append_latest_analysis_warning(
                list(ticket.warnings),
                ready_candidates_by_id[ticket.readiness_id],
            ),
            "readinessStatus": "ready",
            "lastAnalysisError": ready_candidates_by_id[ticket.readiness_id].get("lastAnalysisError"),
            "lastAnalysisFailedAt": ready_candidates_by_id[ticket.readiness_id].get("lastAnalysisFailedAt"),
        }
        for ticket in recommendation.tickets
    ]

    backlog_extras = [
        item
        for item in candidates
        if item.get("readinessStatus") != "ready"
    ]
    backlog_extras.sort(
        key=lambda item: (
            0 if item.get("readinessStatus") == "needs_clarification" else 1,
            PRIORITY_RANK.get(
                str((item.get("jiraSnapshot") or {}).get("priority") or "medium").lower(),
                2,
            ),
            item["jiraKey"],
        )
    )
    for item in backlog_extras:
        if item.get("readinessStatus") == "ready" and item["jiraKey"] in selected_ready_keys:
            continue
        status = str(item.get("readinessStatus") or "")
        warnings: list[str] = []
        if status == "needs_clarification":
            warnings.append("Needs clarification before development")
        elif status == "not_ready":
            warnings.append("Not ready for autonomous delivery")
        elif status == "analysis_failed":
            warnings.append(_ANALYSIS_FAILED_WARNING)
        _append_latest_analysis_warning(warnings, item)
        tickets_payload.append(
            {
                "readinessId": item["readinessId"],
                "jiraKey": item["jiraKey"],
                "title": item["title"],
                "estimatedDays": item["estimatedDays"],
                "priorityRank": _priority_rank(item.get("jiraSnapshot") or {}),
                "urgencyScore": 0.0,
                "warnings": warnings,
                "readinessStatus": status,
                "lastAnalysisError": item.get("lastAnalysisError"),
                "lastAnalysisFailedAt": item.get("lastAnalysisFailedAt"),
            }
        )

    return {
        "sprintName": recommendation.sprint_name,
        "capacityDays": recommendation.capacity_days,
        "usedDays": recommendation.used_days,
        "durationDays": recommendation.duration_days,
        "overflowRisk": recommendation.overflow_risk,
        "warnings": recommendation.warnings,
        "tickets": tickets_payload,
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

    used_days = sprint_capacity_used_days(tickets)
    capacity_days = float(payload.get("capacityDays") or 0)

    merged = dict(payload)
    merged["tickets"] = tickets
    merged["usedDays"] = used_days
    merged["overflowRisk"] = used_days > capacity_days + 0.01 if capacity_days > 0 else bool(payload.get("overflowRisk"))
    merged["activeDevelopmentCount"] = sum(1 for item in tickets if item.get("inDevelopment"))
    return merged


def _ticket_counts_toward_sprint_capacity(item: dict[str, Any]) -> bool:
    if item.get("inDevelopment"):
        return False
    status = str(item.get("readinessStatus") or item.get("readiness_status") or "ready").strip().lower()
    return status == "ready"


def sprint_capacity_used_days(tickets: list[dict[str, Any]]) -> float:
    """Sum estimates for sprint-ready backlog tickets; in-flight carry-over work is excluded."""
    total = 0.0
    for item in tickets:
        if not _ticket_counts_toward_sprint_capacity(item):
            continue
        total += float(item.get("estimatedDays") or item.get("estimated_days") or 0)
    return round(total, 2)


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


def should_keep_empty_backlog(state: dict[str, Any] | None) -> bool:
    """True when a manual reset intentionally cleared sprint tickets until daily analysis."""
    if not state:
        return False
    memory = state.get("memory") if isinstance(state.get("memory"), dict) else {}
    recommendation = state.get("recommendation") if isinstance(state.get("recommendation"), dict) else {}
    if memory.get("emptyBacklogUntilAnalysis"):
        return True
    tickets = recommendation.get("tickets") or []
    return bool(memory.get("lastResetAt")) and not tickets


def load_selected_sprint_payload(*, project_key: str) -> dict[str, Any]:
    """Return persisted sprint selection when stored, else rebuild."""
    from delivery_runtime.pm_inbox.sprint_reset import maybe_auto_reset_sprint

    project_key = project_key.strip().upper()
    auto_reset = maybe_auto_reset_sprint(project_key=project_key)
    if auto_reset is not None:
        return auto_reset

    state = pm_store.get_sprint_state(project_key=project_key)
    if state:
        recommendation = state.get("recommendation") or {}
        if isinstance(recommendation, dict) and "tickets" in recommendation:
            if should_keep_empty_backlog(state):
                return dict(recommendation)
            merged = merge_active_work_orders_into_sprint(recommendation, project_key=project_key)
            return _merge_latest_analysis_failure_warnings(merged, project_key=project_key)

    merged = merge_active_work_orders_into_sprint(
        build_selected_sprint_payload(project_key=project_key),
        project_key=project_key,
    )
    return _merge_latest_analysis_failure_warnings(merged, project_key=project_key)
