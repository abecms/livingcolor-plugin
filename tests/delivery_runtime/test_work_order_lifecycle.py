"""Tests for readiness promotion and work order creation."""

from delivery_runtime.persistence.db import connect, init_db, json_dumps, next_public_id, utc_now_iso
from delivery_runtime.readiness.service import ReadinessService


def _insert_ready_record(conn, *, jira_key: str = "AAC-1", score: int = 82) -> str:
    record_id = next_public_id(conn, "RD")
    now = utc_now_iso()
    snapshot = {
        "key": jira_key,
        "summary": "Implement OAuth callback",
        "description": "Acceptance criteria: store token after OAuth completes.",
        "status": "To Do",
        "issueType": "Story",
        "projectKey": "AAC",
        "priority": "High",
    }
    conn.execute(
        """
        INSERT INTO readiness_records (
            id, jira_key, project_key, title, readiness_score, readiness_status,
            analysis_summary, blockers_json, recommended_repos_json, confidence,
            jira_snapshot_json, analyzed_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'ready', ?, '[]', ?, 0.82, ?, ?, ?, ?)
        """,
        (
            record_id,
            jira_key,
            "AAC",
            snapshot["summary"],
            score,
            "Ticket looks ready for delivery.",
            json_dumps(["gitlab.com/org/app"]),
            json_dumps(snapshot),
            now,
            now,
            now,
        ),
    )
    return record_id


def test_promote_ready_record_creates_work_order_and_graph(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        record_id = _insert_ready_record(conn)

    service = ReadinessService()
    work_order = service.promote(record_id)

    assert work_order["id"].startswith("WO-")
    assert work_order["jiraKey"] == "AAC-1"
    assert work_order["status"] == "intake"
    assert work_order["currentStage"] == "intake"
    assert len(work_order["graphNodes"]) == 5
    assert [node["nodeType"] for node in work_order["graphNodes"]] == [
        "implementation_plan",
        "development",
        "qa_validation",
        "mr_creation",
        "jira_update",
    ]
    assert work_order["graphNodes"][0]["status"] == "ready"

    record = service.get_record(record_id)
    assert record is not None
    assert record["readinessStatus"] == "promoted"
    assert record["promotedWorkOrderId"] == work_order["id"]


def test_promote_rejects_non_ready_record(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        record_id = _insert_ready_record(conn)
        conn.execute(
            "UPDATE readiness_records SET readiness_status = 'not_ready' WHERE id = ?",
            (record_id,),
        )

    service = ReadinessService()
    try:
        service.promote(record_id)
        raised = False
    except ValueError:
        raised = True
    assert raised
