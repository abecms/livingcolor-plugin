"""Tests for automatic and manual sprint reset."""

from __future__ import annotations

from datetime import UTC, date, datetime

from delivery_runtime.automation.config import save_delivery_project_config
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.pm_inbox.sprint_mutations import persist_manual_sprint
from delivery_runtime.pm_inbox.sprint_reset import (
    maybe_auto_reset_sprint,
    reset_sprint,
    should_auto_reset_sprint,
    sprint_end_date,
)
from delivery_runtime.pm_inbox.sprint_selection import load_selected_sprint_payload
from delivery_runtime.persistence.db import connect, json_dumps


def _seed_ready_ticket(*, project_key: str, jira_key: str, estimated_days: float) -> str:
    now = "2026-06-16T10:00:00+00:00"
    readiness_id = f"RD-{jira_key}"
    snapshot = json_dumps(
        {
            "key": jira_key,
            "summary": f"Title {jira_key}",
            "status": "To Do",
            "statusCategory": "To Do",
        }
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO readiness_records (
                id, jira_key, project_key, title, readiness_score, readiness_status,
                analysis_summary, blockers_json, recommended_repos_json, confidence,
                jira_snapshot_json, analyzed_at, promoted_work_order_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 80, 'ready', '', '[]', '[]', 0.8, ?, ?, NULL, ?, ?)
            """,
            (readiness_id, jira_key, project_key, f"Title {jira_key}", snapshot, now, now, now),
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


def test_sprint_end_date_spans_configured_duration():
    start = date(2026, 6, 3)  # Wednesday
    assert sprint_end_date(start=start, duration_days=14) == date(2026, 6, 16)
    assert sprint_end_date(start=start, duration_days=1) == date(2026, 6, 3)


def test_manual_reset_clears_manual_override_and_empties_sprint(_isolate_hermes_home):
    project_key = "TVP"
    _seed_ready_ticket(project_key=project_key, jira_key="TVP-1", estimated_days=1.0)
    save_delivery_project_config(
        duration_days=14,
        capacity_days=15,
        start_weekday=3,
        project_key=project_key,
    )

    persist_manual_sprint(
        project_key=project_key,
        payload={
            "sprintName": "LivingColor Sprint",
            "capacityDays": 15,
            "usedDays": 1,
            "durationDays": 14,
            "overflowRisk": False,
            "warnings": [],
            "tickets": [{"readinessId": "RD-TVP-1", "jiraKey": "TVP-1", "title": "Title", "estimatedDays": 1}],
        },
    )

    wednesday = datetime(2026, 6, 3, 9, 0, tzinfo=UTC)
    payload = reset_sprint(project_key=project_key, now=wednesday, repopulate_tickets=False)

    assert payload["tickets"] == []
    assert payload["usedDays"] == 0
    assert payload["sprintName"] == "LivingColor Sprint 1"
    state = pm_store.get_sprint_state(project_key=project_key)
    assert state is not None
    memory = state["memory"]
    assert memory["manualOverride"] is False
    assert memory["sprintNumber"] == 1
    assert memory["sprintStartDate"] == "2026-06-03"
    assert memory["sprintEndDate"] == "2026-06-16"


def test_auto_reset_waits_for_duration_on_start_weekday(_isolate_hermes_home):
    project_key = "TVP"
    _seed_ready_ticket(project_key=project_key, jira_key="TVP-2", estimated_days=1.0)
    save_delivery_project_config(
        duration_days=14,
        capacity_days=15,
        start_weekday=1,
        project_key=project_key,
    )

    first_monday = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
    assert should_auto_reset_sprint(project_key=project_key, now=first_monday) is True
    first = maybe_auto_reset_sprint(project_key=project_key, now=first_monday)
    assert first is not None
    assert first["sprintName"] == "LivingColor Sprint 1"

    next_monday = datetime(2026, 6, 8, 8, 0, tzinfo=UTC)
    assert should_auto_reset_sprint(project_key=project_key, now=next_monday) is False
    assert maybe_auto_reset_sprint(project_key=project_key, now=next_monday) is None

    third_monday = datetime(2026, 6, 15, 8, 0, tzinfo=UTC)
    assert should_auto_reset_sprint(project_key=project_key, now=third_monday) is True
    second = maybe_auto_reset_sprint(project_key=project_key, now=third_monday)
    assert second is not None
    assert second["sprintName"] == "LivingColor Sprint 2"


def test_auto_reset_ignores_non_start_weekdays(_isolate_hermes_home):
    project_key = "TVP"
    save_delivery_project_config(
        duration_days=7,
        capacity_days=15,
        start_weekday=3,
        project_key=project_key,
    )

    tuesday = datetime(2026, 6, 2, 8, 0, tzinfo=UTC)
    assert should_auto_reset_sprint(project_key=project_key, now=tuesday) is False


def test_load_selected_sprint_payload_keeps_number_after_reset(_isolate_hermes_home):
    project_key = "TVP"
    _seed_ready_ticket(project_key=project_key, jira_key="TVP-3", estimated_days=2.0)
    save_delivery_project_config(
        duration_days=14,
        capacity_days=15,
        start_weekday=1,
        project_key=project_key,
    )

    monday = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)
    reset_sprint(project_key=project_key, now=monday, repopulate_tickets=True)
    payload = load_selected_sprint_payload(project_key=project_key)
    assert payload["sprintName"] == "LivingColor Sprint 1"


def test_load_selected_sprint_payload_keeps_empty_sprint_after_manual_reset(_isolate_hermes_home):
    project_key = "TVP"
    _seed_ready_ticket(project_key=project_key, jira_key="TVP-2138", estimated_days=1.0)
    save_delivery_project_config(
        duration_days=14,
        capacity_days=2,
        start_weekday=1,
        project_key=project_key,
    )

    reset_sprint(project_key=project_key, repopulate_tickets=False)
    payload = load_selected_sprint_payload(project_key=project_key)

    assert payload["tickets"] == []
    assert payload["usedDays"] == 0
    state = pm_store.get_sprint_state(project_key=project_key)
    assert state is not None
    assert state["memory"]["emptyBacklogUntilAnalysis"] is True


def test_daily_rebuild_refills_sprint_after_manual_reset(_isolate_hermes_home):
    from delivery_runtime.pm_inbox.daily_pipeline import DailyAnalysisPipeline

    project_key = "TVP"
    _seed_ready_ticket(project_key=project_key, jira_key="TVP-2140", estimated_days=1.0)
    save_delivery_project_config(
        duration_days=14,
        capacity_days=2,
        start_weekday=1,
        project_key=project_key,
    )

    reset_sprint(project_key=project_key, repopulate_tickets=False)
    pipeline = DailyAnalysisPipeline()
    payload = pipeline._rebuild_selected_sprint(project_key=project_key)

    assert payload["tickets"]
    assert payload["tickets"][0]["jiraKey"] == "TVP-2140"
    state = pm_store.get_sprint_state(project_key=project_key)
    assert state is not None
    assert state["memory"]["emptyBacklogUntilAnalysis"] is False
