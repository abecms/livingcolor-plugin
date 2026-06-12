"""Tests for keeping in-flight work orders visible in sprint selection."""

from __future__ import annotations

from delivery_runtime.persistence.db import connect, init_db, json_dumps, next_public_id, utc_now_iso
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
