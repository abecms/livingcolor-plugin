"""Tests for refreshing stored Jira comment proposals after language changes."""

from __future__ import annotations

from delivery_runtime.automation.config import save_delivery_project_config
from delivery_runtime.persistence.db import connect, init_db, json_dumps, next_public_id, utc_now_iso
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.pm_inbox.daily_pipeline import refresh_project_communications
from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping


def test_refresh_project_communications_rewrites_pending_proposals_in_french(tmp_path, monkeypatch):
    from delivery_runtime.automation import config as automation_config

    home = tmp_path / "livingcolor"
    monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: home)
    install_phase25_project_mapping()
    init_db()

    snapshot = json_dumps(
        {
            "key": "BN-346",
            "summary": "Audio replay",
            "description": "Broken replay",
            "status": "To Do",
            "statusCategory": "To Do",
            "issueType": "Bug",
            "projectKey": "BN",
        }
    )

    with connect() as conn:
        record_id = next_public_id(conn, "RD")
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO readiness_records (
                id, jira_key, project_key, title, readiness_score, readiness_status,
                analysis_summary, blockers_json, recommended_repos_json, confidence,
                jira_snapshot_json, analyzed_at, created_at, updated_at
            ) VALUES (?, 'BN-346', 'BN', 'Audio replay', 40, 'needs_clarification',
                      'Needs info', '[]', '[]', 0.4, ?, ?, ?, ?)
            """,
            (record_id, snapshot, now, now, now),
        )
        pm_store.upsert_comment_proposal(
            conn,
            readiness_id=record_id,
            jira_key="BN-346",
            proposal_type="needs_clarification",
            body="I do not currently have enough information to work on this ticket.",
        )

    save_delivery_project_config(
        capacity_days=15,
        duration_days=14,
        communication_language="fr",
    )

    with connect() as conn:
        row = conn.execute(
            "SELECT body FROM jira_comment_proposals WHERE jira_key = 'BN-346' AND status = 'pending'"
        ).fetchone()

    assert row is not None
    assert "Je n'ai pas actuellement assez d'informations" in row["body"]

    refresh = refresh_project_communications("BN")
    assert refresh["proposalsCreated"] >= 1

    with connect() as conn:
        row = conn.execute(
            "SELECT body FROM jira_comment_proposals WHERE jira_key = 'BN-346' AND status = 'pending'"
        ).fetchone()

    assert "étapes de reproduction" in row["body"].lower()
