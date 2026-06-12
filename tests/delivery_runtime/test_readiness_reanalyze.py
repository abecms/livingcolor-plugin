"""Tests for readiness re-analysis with Hermes analyst and Jira comments."""

from __future__ import annotations

from delivery_runtime.events.store import EventStore
from delivery_runtime.persistence.db import connect, init_db, json_dumps, next_public_id, utc_now_iso
from delivery_runtime.readiness.errors import ReadinessIntegrationError
from delivery_runtime.readiness.service import ReadinessService


def _insert_record(conn, *, jira_key: str = "TVP-42") -> str:
    record_id = next_public_id(conn, "RD")
    now = utc_now_iso()
    snapshot = {
        "key": jira_key,
        "summary": "Fix checkout regression",
        "description": "Original acceptance criteria from the ticket body.",
        "status": "Reopened",
        "issueType": "Bug",
        "projectKey": "TVP",
    }
    conn.execute(
        """
        INSERT INTO readiness_records (
            id, jira_key, project_key, title, readiness_score, readiness_status,
            analysis_summary, blockers_json, recommended_repos_json, confidence,
            jira_snapshot_json, analyzed_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 40, 'not_ready', 'Old analysis', '[]', '[]', 0.4, ?, ?, ?, ?)
        """,
        (
            record_id,
            jira_key,
            "TVP",
            snapshot["summary"],
            json_dumps(snapshot),
            now,
            now,
            now,
        ),
    )
    return record_id


def test_reanalyze_uses_analysis_runner_and_persists_refreshed_snapshot(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        record_id = _insert_record(conn)

    refreshed_snapshot = {
        "key": "TVP-42",
        "summary": "Fix checkout regression",
        "description": "Original acceptance criteria from the ticket body.",
        "status": "Reopened",
        "issueType": "Bug",
        "projectKey": "TVP",
        "comments": [
            {
                "author": "QA Lead",
                "body": "Ticket reopened: payment step still fails on Safari.",
                "created": "2026-06-10T09:00:00.000+0000",
            }
        ],
        "commentCount": 1,
        "isReopened": True,
    }
    captured: dict[str, object] = {}

    def fake_refresher(jira_key: str) -> dict:
        assert jira_key == "TVP-42"
        return dict(refreshed_snapshot)

    def fake_runner(snapshot: dict, project_key: str) -> dict:
        captured["snapshot"] = snapshot
        captured["project_key"] = project_key
        return {
            "readinessScore": 55,
            "readinessStatus": "not_ready",
            "analysisSummary": "QA comment shows unresolved Safari failure.",
            "blockers": ["Unresolved QA feedback in Jira comments"],
            "recommendedRepos": ["group/tvp-web"],
            "confidence": 0.7,
            "jiraSnapshot": snapshot,
        }

    events = EventStore()
    service = ReadinessService(
        events,
        analysis_runner=fake_runner,
        issue_refresher=fake_refresher,
    )

    updated = service.reanalyze(record_id)

    assert captured["project_key"] == "TVP"
    assert captured["snapshot"]["reanalyzeContext"] is True
    assert captured["snapshot"]["comments"][0]["body"].startswith("Ticket reopened")
    assert updated["readinessScore"] == 55
    assert updated["readinessStatus"] == "not_ready"
    assert updated["jiraSnapshot"]["comments"][0]["author"] == "QA Lead"
    assert "reanalyzeContext" not in updated["jiraSnapshot"]

    completed = [
        event
        for event in events.list_recent(limit=20)
        if event["eventType"] == "READINESS_ANALYSIS_COMPLETED"
    ]
    assert completed[-1]["payload"]["reanalyze"] is True
    assert completed[-1]["payload"]["refreshedFromJira"] is True
    assert completed[-1]["payload"]["commentCount"] == 1


def test_reanalyze_persists_estimated_days(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        record_id = _insert_record(conn, jira_key="TVP-77")

    def fake_runner(snapshot: dict, project_key: str) -> dict:
        return {
            "readinessScore": 80,
            "readinessStatus": "ready",
            "analysisSummary": "Clear scope.",
            "blockers": [],
            "recommendedRepos": [],
            "confidence": 0.8,
            "estimatedDays": 1.5,
            "jiraSnapshot": snapshot,
        }

    service = ReadinessService(analysis_runner=fake_runner)
    updated = service.reanalyze(record_id)

    assert updated["estimatedDays"] == 1.5

    with connect() as conn:
        row = conn.execute(
            "SELECT estimated_days FROM readiness_records WHERE id = ?",
            (record_id,),
        ).fetchone()
    assert row["estimated_days"] == 1.5


def test_reanalyze_falls_back_to_stored_snapshot_when_jira_refresh_fails(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        record_id = _insert_record(conn, jira_key="TVP-99")

    def failing_refresher(_jira_key: str) -> dict:
        raise ReadinessIntegrationError("Jira unavailable")

    def fake_runner(snapshot: dict, project_key: str) -> dict:
        return {
            "readinessScore": 60,
            "readinessStatus": "not_ready",
            "analysisSummary": "Used stored snapshot.",
            "blockers": [],
            "recommendedRepos": [],
            "confidence": 0.6,
            "jiraSnapshot": snapshot,
        }

    service = ReadinessService(
        analysis_runner=fake_runner,
        issue_refresher=failing_refresher,
    )
    updated = service.reanalyze(record_id)

    assert updated["readinessScore"] == 60
    assert updated["jiraSnapshot"]["key"] == "TVP-99"
    assert "comments" not in updated["jiraSnapshot"]
