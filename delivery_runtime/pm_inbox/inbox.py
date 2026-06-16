"""PM Inbox / Execution Queue payload builder."""

from __future__ import annotations

from typing import Any

from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.persistence.db import connect, json_loads
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.pm_inbox.sprint_selection import load_selected_sprint_payload
from delivery_runtime.readiness.project_settings import resolve_jira_browse_base_url
from delivery_runtime.readiness.ticket_scope import load_ticket_scope_for_project, matches_ticket_scope


def _readiness_row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "jiraKey": row["jira_key"],
        "projectKey": row["project_key"],
        "title": row["title"],
        "readinessScore": row["readiness_score"],
        "readinessStatus": row["readiness_status"],
        "analysisSummary": row["analysis_summary"],
        "blockers": json_loads(row["blockers_json"], []),
        "recommendedRepos": json_loads(row["recommended_repos_json"], []),
        "confidence": row["confidence"],
        "jiraSnapshot": json_loads(row["jira_snapshot_json"], {}),
        "analyzedAt": row["analyzed_at"],
        "promotedWorkOrderId": row["promoted_work_order_id"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _normalize_queue_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "readinessId": item.get("readinessId") or item.get("readiness_id"),
        "jiraKey": item.get("jiraKey") or item.get("jira_key"),
        "title": item.get("title") or item.get("jiraKey"),
        "queueStatus": item.get("queueStatus") or item.get("queue_status"),
        "priorityScore": item.get("priorityScore") if "priorityScore" in item else item.get("priority_score"),
        "estimatedDays": item.get("estimatedDays") if "estimatedDays" in item else item.get("estimated_days"),
        "complexity": item.get("complexity"),
        "confidence": item.get("confidence"),
        "blockers": item.get("blockers") or [],
        "priorityFactors": item.get("priorityFactors") or item.get("priority_factors") or {},
        "position": item.get("position") or 0,
        "recommendedNext": bool(item.get("recommendedNext") or item.get("recommended_next")),
    }


def _in_selected_sprint(jira_key: str | None, sprint_keys: set[str]) -> bool:
    if not sprint_keys or not jira_key:
        return False
    return jira_key in sprint_keys


def build_pm_inbox(*, project_key: str | None = None, queue_consumer: Any | None = None) -> dict[str, Any]:
    config = load_delivery_automation_config()
    project_key = (project_key or config.project_key).strip().upper()
    project_name = config.project_name
    ticket_scope = load_ticket_scope_for_project(project_key)
    latest_run = pm_store.get_latest_daily_run(project_key=project_key)
    execution_queue = pm_store.get_execution_queue(project_key=project_key)
    project_memory_row = pm_store.get_project_memory(project_key=project_key)
    selected_sprint = load_selected_sprint_payload(project_key=project_key)
    sprint_keys = {ticket["jiraKey"] for ticket in selected_sprint.get("tickets", [])}
    latest_pipeline = latest_run.get("pipeline") if isinstance(latest_run, dict) else None
    analysis_dispatch = (
        latest_pipeline.get("analysisDispatch")
        if isinstance(latest_pipeline, dict) and isinstance(latest_pipeline.get("analysisDispatch"), dict)
        else None
    )

    current_active = None
    if queue_consumer is not None:
        active = queue_consumer.get_active_development(project_key)
        if active and _in_selected_sprint(active.get("jiraKey"), sprint_keys):
            current_active = active

    with connect() as conn:
        readiness_rows = conn.execute(
            """
            SELECT * FROM readiness_records
            WHERE project_key = ? AND readiness_status NOT IN ('promoted', 'dismissed')
            ORDER BY updated_at DESC
            """,
            (project_key,),
        ).fetchall()

        pending_gates = conn.execute(
            """
            SELECT g.id, g.work_order_id, g.gate_type, g.status, g.payload_json, g.created_at,
                   wo.jira_key, wo.title, wo.current_stage, wo.status AS work_order_status
            FROM gates g
            INNER JOIN work_orders wo ON wo.id = g.work_order_id
            WHERE g.status = 'pending' AND wo.jira_key LIKE ?
            ORDER BY g.created_at DESC
            """,
            (f"{project_key}-%",),
        ).fetchall()

        active_developments = conn.execute(
            """
            SELECT id, jira_key, title, current_stage, status, updated_at
            FROM work_orders
            WHERE jira_key LIKE ? AND status NOT IN ('completed', 'cancelled', 'failed')
            ORDER BY updated_at DESC
            """,
            (f"{project_key}-%",),
        ).fetchall()

    proposals = pm_store.list_pending_proposals(project_key=project_key)
    proposals_by_readiness = {item["readinessId"]: item for item in proposals if item.get("readinessId")}

    needs_clarification = []
    for row in readiness_rows:
        record = _readiness_row_to_dict(row)
        if record["readinessStatus"] != "needs_clarification":
            continue
        if not matches_ticket_scope(record.get("jiraSnapshot") or {}, ticket_scope):
            continue
        needs_clarification.append(
            {
                "record": record,
                "detectedIssues": record["blockers"],
                "proposal": proposals_by_readiness.get(record["id"]),
            }
        )

    waiting_for_approval = []
    gate_labels = {
        "analysis_plan": "Analysis validation",
        "code_review": "Patch / MR validation",
        "merge_request_review": "Patch / MR validation",
        "merge_request": "Patch / MR validation",
        "jira_update": "Jira update validation",
    }
    for gate in pending_gates:
        if not _in_selected_sprint(gate["jira_key"], sprint_keys):
            continue
        waiting_for_approval.append(
            {
                "kind": "gate",
                "gateId": gate["id"],
                "workOrderId": gate["work_order_id"],
                "jiraKey": gate["jira_key"],
                "title": gate["title"],
                "gateType": gate["gate_type"],
                "label": gate_labels.get(gate["gate_type"], "Approval required"),
                "createdAt": gate["created_at"],
            }
        )
    for proposal in proposals:
        if proposal.get("proposalType") in {"needs_clarification", "not_development"}:
            continue
        if not _in_selected_sprint(proposal.get("jiraKey"), sprint_keys):
            continue
        waiting_for_approval.append(
            {
                "kind": "jira_comment",
                "proposalId": proposal["id"],
                "jiraKey": proposal["jiraKey"],
                "label": "Client communication validation",
                "proposalType": proposal["proposalType"],
                "body": proposal["body"],
                "createdAt": proposal["createdAt"],
            }
        )

    normalized_queue = [
        _normalize_queue_item(item)
        for item in execution_queue.get("items", [])
        if _in_selected_sprint(item.get("jiraKey") or item.get("jira_key"), sprint_keys)
    ]
    recommended_next = execution_queue.get("recommendedNext")
    if recommended_next:
        recommended_next = _normalize_queue_item(recommended_next)
        if not _in_selected_sprint(recommended_next.get("jiraKey"), sprint_keys):
            recommended_next = None

    if sprint_keys and normalized_queue:
        recommended_next = normalized_queue[0]

    sprint_executable_count = sum(1 for item in normalized_queue if item.get("queueStatus") == "executable")
    sprint_blocked_count = sum(
        1 for item in normalized_queue if item.get("queueStatus") not in ("executable", "in_progress")
    )

    return {
        "projectKey": project_key,
        "projectName": project_name,
        "productIdentity": "Autonomous Development Scheduler",
        "jiraBrowseBaseUrl": resolve_jira_browse_base_url(project_key),
        "lastRun": latest_run,
        "analysisDispatch": analysis_dispatch,
        "recommendedNext": recommended_next,
        "currentActiveDelivery": current_active,
        "executionQueue": {
            "items": normalized_queue,
            "executableCount": sprint_executable_count,
            "blockedCount": sprint_blocked_count,
        },
        "selectedSprint": selected_sprint,
        "needsClarification": needs_clarification,
        "waitingForApproval": waiting_for_approval,
        "activeDevelopments": [
            {
                "workOrderId": row["id"],
                "jiraKey": row["jira_key"],
                "title": row["title"],
                "currentStage": row["current_stage"],
                "status": row["status"],
                "updatedAt": row["updated_at"],
            }
            for row in active_developments
        ],
        "projectMemoryHighlights": (project_memory_row or {}).get("highlights", []),
        "projectMemory": (project_memory_row or {}).get("memory", {}),
    }
