"""Tests for manual sprint and estimation mutations."""

from __future__ import annotations

from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.pm_inbox.service import PmInboxService
from delivery_runtime.pm_inbox.sprint_selection import load_selected_sprint_payload
from delivery_runtime.persistence.db import connect


def _seed_ready_ticket(*, project_key: str, jira_key: str, estimated_days: float) -> str:
    now = "2026-06-10T10:00:00+00:00"
    readiness_id = f"RD-{jira_key}"
    with connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO readiness_records (
                id, jira_key, project_key, title, readiness_score, readiness_status,
                analysis_summary, blockers_json, recommended_repos_json, confidence,
                jira_snapshot_json, analyzed_at, promoted_work_order_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 80, 'ready', '', '[]', '[]', 0.8, '{}', ?, NULL, ?, ?)
            """,
            (readiness_id, jira_key, project_key, f"Title {jira_key}", now, now, now),
        )
        pm_store.insert_estimation(
            conn,
            readiness_id=readiness_id,
            jira_key=jira_key,
            complexity="medium",
            estimated_days=estimated_days,
            confidence=0.8,
            run_id="test",
        )
    return readiness_id


def test_update_estimation_and_sprint_exclude(_isolate_hermes_home):
    project_key = "TVP"
    _seed_ready_ticket(project_key=project_key, jira_key="TVP-1", estimated_days=1.0)
    _seed_ready_ticket(project_key=project_key, jira_key="TVP-2", estimated_days=1.0)

    service = PmInboxService()
    service.update_ticket_estimation(
        project_key=project_key,
        jira_key="TVP-1",
        estimated_days=0.875,
    )
    payload = service.update_sprint_selection(
        project_key=project_key,
        tickets=["TVP-1", "TVP-2"],
    )
    assert [ticket["jiraKey"] for ticket in payload["tickets"]] == ["TVP-1", "TVP-2"]

    updated = service.update_sprint_selection(project_key=project_key, exclude=["TVP-2"])
    assert [ticket["jiraKey"] for ticket in updated["tickets"]] == ["TVP-1"]

    sprint = load_selected_sprint_payload(project_key=project_key)
    assert sprint["tickets"][0]["jiraKey"] == "TVP-1"
    assert sprint["tickets"][0]["estimatedDays"] == 0.875


def test_swap_sprint_tickets(_isolate_hermes_home):
    project_key = "TVP"
    _seed_ready_ticket(project_key=project_key, jira_key="TVP-10", estimated_days=1.0)
    _seed_ready_ticket(project_key=project_key, jira_key="TVP-20", estimated_days=2.0)

    service = PmInboxService()
    service.update_sprint_selection(project_key=project_key, tickets=["TVP-10", "TVP-20"])
    swapped = service.update_sprint_selection(
        project_key=project_key,
        swap={"a": "TVP-10", "b": "TVP-20"},
    )
    assert [ticket["jiraKey"] for ticket in swapped["tickets"]] == ["TVP-20", "TVP-10"]
