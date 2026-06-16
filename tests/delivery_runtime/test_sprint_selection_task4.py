from __future__ import annotations

from delivery_runtime.persistence.db import connect, init_db, json_dumps, utc_now_iso
from delivery_runtime.pm_inbox.sprint_selection import build_selected_sprint_payload


def test_sprint_backlog_excludes_ready_overflow_tickets(_isolate_hermes_home):
    from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping

    install_phase25_project_mapping()
    init_db()
    now = utc_now_iso()
    records = [
        ("RD-901", "TVP-901", "Selected ready", "ready", 90, 10.0, {"priority": "High"}),
        ("RD-902", "TVP-902", "Overflow ready", "ready", 88, 10.0, {"priority": "Low"}),
        (
            "RD-903",
            "TVP-903",
            "Visible failed analysis",
            "analysis_failed",
            0,
            0.0,
            {"priority": "Medium"},
        ),
    ]
    with connect() as conn:
        for record_id, jira_key, title, status, score, estimated_days, snapshot_patch in records:
            snapshot = {
                "key": jira_key,
                "summary": title,
                "description": title,
                "status": "To Do",
                "issueType": "Story",
                "projectKey": "TVP",
                **snapshot_patch,
            }
            conn.execute(
                """
                INSERT INTO readiness_records (
                    id, jira_key, project_key, title, readiness_score, readiness_status,
                    analysis_summary, blockers_json, recommended_repos_json, confidence,
                    estimated_days, jira_snapshot_json, analyzed_at, created_at, updated_at
                ) VALUES (?, ?, 'TVP', ?, ?, ?, 'Analysis summary', '[]', '[]', 0.8,
                          ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    jira_key,
                    title,
                    score,
                    status,
                    estimated_days,
                    json_dumps(snapshot),
                    now,
                    now,
                    now,
                ),
            )

    payload = build_selected_sprint_payload(project_key="TVP")
    tickets = {ticket["jiraKey"]: ticket for ticket in payload["tickets"]}

    assert "TVP-901" in tickets
    assert "TVP-902" not in tickets
    assert "TVP-903" in tickets
    assert tickets["TVP-903"]["readinessStatus"] == "analysis_failed"
    assert payload["usedDays"] == 10.0
    assert payload["capacityDays"] == 15.0
