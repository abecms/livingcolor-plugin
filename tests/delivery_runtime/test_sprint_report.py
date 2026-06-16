"""Tests for sprint retrospective publishing."""

from __future__ import annotations

from datetime import UTC, datetime

from delivery_runtime.automation.config import save_delivery_project_config
from delivery_runtime.persistence.db import connect, utc_now_iso
from delivery_runtime.pm_inbox.sprint_report import (
    build_sprint_report_snapshot,
    publish_sprint_report,
    should_run_scheduled_sprint_report,
    sprint_report_dedup_key,
)
from delivery_runtime.pm_inbox.sprint_selection import persist_selected_sprint


def _seed_sprint_state(*, project_key: str, sprint_number: int, end_date: str) -> None:
    payload = {
        "sprintName": f"Sprint {sprint_number}",
        "capacityDays": 15.0,
        "usedDays": 5.0,
        "durationDays": 14,
        "overflowRisk": False,
        "warnings": [],
        "tickets": [
            {
                "readinessId": "RD-BN-1",
                "jiraKey": "BN-1",
                "title": "First ticket",
                "estimatedDays": 2.0,
                "priorityRank": 1,
                "urgencyScore": 1.0,
                "warnings": [],
            }
        ],
    }
    persist_selected_sprint(
        project_key=project_key,
        payload=payload,
        memory_patch={
            "sprintNumber": sprint_number,
            "sprintStartDate": "2026-06-03",
            "sprintEndDate": end_date,
        },
    )


def test_build_sprint_report_snapshot_includes_work_orders(_isolate_hermes_home):
    project_key = "BN"
    save_delivery_project_config(duration_days=14, capacity_days=15, project_key=project_key)
    _seed_sprint_state(project_key=project_key, sprint_number=3, end_date="2026-06-16")

    now = utc_now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO work_orders (
                id, jira_key, readiness_id, title, description, priority, status,
                current_stage, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("WO-1", "BN-1", "RD-BN-1", "First ticket", "", "High", "completed", "done", 0.9, now, now),
        )

    snapshot = build_sprint_report_snapshot(project_key=project_key)
    assert snapshot is not None
    assert snapshot["sprintNumber"] == 3
    assert snapshot["ticketsPlanned"][0]["jiraKey"] == "BN-1"
    assert snapshot["workOrderStatusCounts"]["completed"] == 1
    assert snapshot["deliveredTicketKeys"] == ["BN-1"]


def test_publish_sprint_report_sends_and_deduplicates(_isolate_hermes_home):
    project_key = "BN"
    save_delivery_project_config(duration_days=14, capacity_days=15, project_key=project_key)
    _seed_sprint_state(project_key=project_key, sprint_number=2, end_date="2026-06-16")

    sent_messages: list[str] = []

    def fake_compose(snapshot, key):
        assert key == project_key
        return f"Sprint report for {snapshot['sprint']['name']}"

    def fake_send(message: str):
        sent_messages.append(message)
        return {"success": True, "platform": "slack"}

    first = publish_sprint_report(
        project_key=project_key,
        reporter=fake_compose,
        sender=fake_send,
    )
    assert first["status"] == "sent"
    assert sent_messages == ["Sprint report for Sprint 2"]

    second = publish_sprint_report(
        project_key=project_key,
        reporter=fake_compose,
        sender=fake_send,
    )
    assert second["status"] == "skipped"
    assert second["reason"] == "already_published"
    assert len(sent_messages) == 1


def test_should_run_scheduled_sprint_report_on_end_day(_isolate_hermes_home):
    project_key = "BN"
    save_delivery_project_config(duration_days=14, capacity_days=15, project_key=project_key)
    _seed_sprint_state(project_key=project_key, sprint_number=1, end_date="2026-06-16")

    end_day = datetime(2026, 6, 16, 16, 0, tzinfo=UTC)
    assert should_run_scheduled_sprint_report(project_key=project_key, now=end_day) is True

    wrong_day = datetime(2026, 6, 15, 16, 0, tzinfo=UTC)
    assert should_run_scheduled_sprint_report(project_key=project_key, now=wrong_day) is False


def test_sprint_report_dedup_key_is_stable():
    assert sprint_report_dedup_key(sprint_number=4, sprint_end_date="2026-06-16") == "4:2026-06-16"
