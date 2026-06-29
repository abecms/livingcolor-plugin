"""Tests for keeping in-flight work orders visible in sprint selection."""

from __future__ import annotations

from delivery_runtime.persistence.db import connect, init_db, json_dumps, next_public_id, utc_now_iso
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.pm_inbox.sprint_selection import (
    build_selected_sprint_payload,
    load_selected_sprint_payload,
    merge_active_work_orders_into_sprint,
)


def test_merge_active_work_orders_into_sprint_appends_in_flight_tickets(_isolate_hermes_home):
    payload = {
        "sprintName": "LivingColor Sprint",
        "capacityDays": 2.0,
        "usedDays": 1.0,
        "durationDays": 7,
        "overflowRisk": False,
        "warnings": [],
        "tickets": [
            {
                "readinessId": "RD-1",
                "jiraKey": "TVP-100",
                "title": "Ready ticket",
                "estimatedDays": 1.0,
                "priorityRank": 1,
                "urgencyScore": 1.0,
                "warnings": [],
            }
        ],
    }

    init_db()
    with connect() as conn:
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO work_orders (
                id, jira_key, readiness_id, title, description, priority,
                status, current_stage, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "WO-9",
                "TVP-2254",
                "RD-9",
                "Approved ticket",
                "",
                "",
                "awaiting_gate",
                "clarification",
                0.9,
                now,
                now,
            ),
        )

    merged = merge_active_work_orders_into_sprint(payload, project_key="TVP")

    keys = {ticket["jiraKey"] for ticket in merged["tickets"]}
    assert keys == {"TVP-100", "TVP-2254"}
    in_flight = next(item for item in merged["tickets"] if item["jiraKey"] == "TVP-2254")
    assert in_flight["inDevelopment"] is True
    assert in_flight["workOrderId"] == "WO-9"
    assert in_flight["currentStage"] == "clarification"
    assert merged["activeDevelopmentCount"] == 1
    assert merged["usedDays"] == 1.0


def test_promoted_sprint_ticket_keeps_consuming_capacity(_isolate_hermes_home):
    payload = {
        "sprintName": "LivingColor Sprint",
        "capacityDays": 2.0,
        "usedDays": 2.0,
        "durationDays": 7,
        "overflowRisk": True,
        "warnings": [],
        "tickets": [
            {
                "readinessId": "RD-1",
                "jiraKey": "TVP-100",
                "title": "Was in sprint, now approved",
                "estimatedDays": 2.0,
                "priorityRank": 1,
                "urgencyScore": 1.0,
                "warnings": [],
                "sprintSelected": True,
                "readinessStatus": "ready",
            }
        ],
    }

    init_db()
    with connect() as conn:
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO work_orders (
                id, jira_key, readiness_id, title, description, priority,
                status, current_stage, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "WO-11",
                "TVP-100",
                "RD-1",
                "Was in sprint, now approved",
                "",
                "",
                "awaiting_gate",
                "jira_update",
                0.9,
                now,
                now,
            ),
        )

    merged = merge_active_work_orders_into_sprint(payload, project_key="TVP")

    assert merged["usedDays"] == 2.0
    assert merged["overflowRisk"] is False


def test_load_selected_sprint_payload_includes_promoted_work_orders(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO work_orders (
                id, jira_key, readiness_id, title, description, priority,
                status, current_stage, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "WO-10",
                "TVP-2258",
                "RD-10",
                "Already approved",
                "",
                "",
                "intake",
                "intake",
                0.8,
                now,
                now,
            ),
        )

    payload = load_selected_sprint_payload(project_key="TVP")
    keys = {ticket["jiraKey"] for ticket in payload["tickets"]}

    assert "TVP-2258" in keys
    approved = next(item for item in payload["tickets"] if item["jiraKey"] == "TVP-2258")
    assert approved["inDevelopment"] is True
    assert approved["workOrderId"] == "WO-10"


def test_pm_inbox_response_preserves_sprint_work_order_fields(_isolate_hermes_home):
    from delivery_runtime.api.schemas import PmInboxResponse
    from delivery_runtime.pm_inbox.inbox import build_pm_inbox

    init_db()
    with connect() as conn:
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO work_orders (
                id, jira_key, readiness_id, title, description, priority,
                status, current_stage, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "WO-11",
                "TVP-2260",
                "RD-11",
                "Approved sprint ticket",
                "",
                "",
                "running",
                "intake",
                0.8,
                now,
                now,
            ),
        )

    payload = build_pm_inbox(project_key="TVP")
    validated = PmInboxResponse.model_validate(payload).model_dump()
    approved = next(
        (item for item in validated["selectedSprint"]["tickets"] if item["jiraKey"] == "TVP-2260"),
        None,
    )

    assert approved is not None
    assert approved["workOrderId"] == "WO-11"
    assert approved["inDevelopment"] is True


def test_merge_sprint_used_days_excludes_non_ready_backlog(_isolate_hermes_home):
    payload = {
        "sprintName": "LivingColor Sprint",
        "capacityDays": 2.0,
        "usedDays": 1.0,
        "durationDays": 14,
        "overflowRisk": False,
        "warnings": [],
        "tickets": [
            {
                "readinessId": "RD-1",
                "jiraKey": "BN-100",
                "title": "Ready ticket",
                "estimatedDays": 1.0,
                "priorityRank": 1,
                "urgencyScore": 1.0,
                "warnings": [],
                "readinessStatus": "ready",
            },
            {
                "readinessId": "RD-2",
                "jiraKey": "BN-200",
                "title": "Needs clarification",
                "estimatedDays": 5.0,
                "priorityRank": 2,
                "urgencyScore": 0.0,
                "warnings": ["Needs clarification before development"],
                "readinessStatus": "needs_clarification",
            },
            {
                "readinessId": "RD-3",
                "jiraKey": "BN-300",
                "title": "Not ready",
                "estimatedDays": 3.0,
                "priorityRank": 3,
                "urgencyScore": 0.0,
                "warnings": ["Not ready for autonomous delivery"],
                "readinessStatus": "not_ready",
            },
        ],
    }

    merged = merge_active_work_orders_into_sprint(payload, project_key="BN")

    assert merged["usedDays"] == 1.0
    assert merged["overflowRisk"] is False


def test_sprint_backlog_includes_needs_clarification_tickets(_isolate_hermes_home):
    from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping

    install_phase25_project_mapping()
    init_db()
    now = utc_now_iso()
    snapshot = json_dumps(
        {
            "key": "TVP-900",
            "summary": "Thin ticket",
            "description": "Needs more detail",
            "status": "To Do",
            "issueType": "Bug",
            "projectKey": "TVP",
        }
    )
    with connect() as conn:
        record_id = next_public_id(conn, "RD")
        conn.execute(
            """
            INSERT INTO readiness_records (
                id, jira_key, project_key, title, readiness_score, readiness_status,
                analysis_summary, blockers_json, recommended_repos_json, confidence,
                estimated_days, jira_snapshot_json, analyzed_at, created_at, updated_at
            ) VALUES (?, 'TVP-900', 'TVP', 'Thin ticket', 40, 'needs_clarification',
                      'Needs info', '[]', '[]', 0.4, NULL, ?, ?, ?, ?)
            """,
            (record_id, snapshot, now, now, now),
        )

    payload = build_selected_sprint_payload(project_key="TVP")
    keys = {ticket["jiraKey"] for ticket in payload["tickets"]}
    assert "TVP-900" in keys
    ticket = next(item for item in payload["tickets"] if item["jiraKey"] == "TVP-900")
    assert ticket["readinessStatus"] == "needs_clarification"
    assert ticket["estimatedDays"] is None
    assert payload["usedDays"] == 0.0
