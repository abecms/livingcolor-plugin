"""SQLite persistence for PM Inbox and daily analysis artifacts."""

from __future__ import annotations

import sqlite3
from typing import Any

from delivery_runtime.persistence.db import connect, json_dumps, json_loads, next_public_id, utc_now_iso


def _row_to_run(row) -> dict[str, Any]:
    pipeline = json_loads(row["pipeline_json"], {})
    scan = pipeline.get("scan") if isinstance(pipeline, dict) else {}
    jira_fetched = scan.get("scanned") if isinstance(scan, dict) else None
    return {
        "id": row["id"],
        "projectKey": row["project_key"],
        "startedAt": row["started_at"],
        "completedAt": row["completed_at"],
        "status": row["status"],
        "jiraSynced": row["jira_synced"],
        "jiraFetched": jira_fetched,
        "analyzed": row["analyzed"],
        "estimated": row["estimated"],
        "pipeline": pipeline,
        "errorMessage": row["error_message"],
    }


def _row_to_proposal(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "readinessId": row["readiness_id"],
        "workOrderId": row["work_order_id"],
        "jiraKey": row["jira_key"],
        "proposalType": row["proposal_type"],
        "status": row["status"],
        "body": row["body"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "approvedBy": row["approved_by"],
        "publishedAt": row["published_at"],
    }


def _row_to_estimation(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "readinessId": row["readiness_id"],
        "jiraKey": row["jira_key"],
        "complexity": row["complexity"],
        "estimatedDays": row["estimated_days"],
        "confidence": row["confidence"],
        "createdAt": row["created_at"],
        "runId": row["run_id"],
    }


def create_daily_run(conn, *, project_key: str) -> str:
    run_id = next_public_id(conn, "DA")
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO daily_analysis_runs (
            id, project_key, started_at, status, pipeline_json
        ) VALUES (?, ?, ?, 'running', '{}')
        """,
        (run_id, project_key, now),
    )
    return run_id


def complete_daily_run(
    conn,
    *,
    run_id: str,
    status: str,
    jira_synced: int,
    analyzed: int,
    estimated: int,
    pipeline: dict[str, Any],
    error_message: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE daily_analysis_runs
        SET completed_at = ?, status = ?, jira_synced = ?, analyzed = ?, estimated = ?,
            pipeline_json = ?, error_message = ?
        WHERE id = ?
        """,
        (
            utc_now_iso(),
            status,
            jira_synced,
            analyzed,
            estimated,
            json_dumps(pipeline),
            error_message,
            run_id,
        ),
    )


def get_latest_daily_run(*, project_key: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM daily_analysis_runs
            WHERE project_key = ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (project_key,),
        ).fetchone()
    return _row_to_run(row) if row else None


def get_previous_completed_run(*, project_key: str, before_run_id: str | None = None) -> dict[str, Any] | None:
    clauses = ["project_key = ?", "status = 'completed'"]
    params: list[Any] = [project_key]
    if before_run_id:
        clauses.append("id != ?")
        params.append(before_run_id)

    where = " AND ".join(clauses)
    with connect() as conn:
        row = conn.execute(
            f"""
            SELECT * FROM daily_analysis_runs
            WHERE {where}
            ORDER BY completed_at DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
    return _row_to_run(row) if row else None


def insert_estimation(
    conn,
    *,
    readiness_id: str,
    jira_key: str,
    complexity: str,
    estimated_days: float,
    confidence: float,
    run_id: str,
) -> str:
    estimation_id = next_public_id(conn, "TE")
    conn.execute(
        """
        INSERT INTO ticket_estimations (
            id, readiness_id, jira_key, complexity, estimated_days, confidence, created_at, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            estimation_id,
            readiness_id,
            jira_key,
            complexity,
            estimated_days,
            confidence,
            utc_now_iso(),
            run_id,
        ),
    )
    return estimation_id


def get_readiness_record_by_jira_key(*, project_key: str, jira_key: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM readiness_records
            WHERE project_key = ? AND jira_key = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (project_key.strip().upper(), jira_key.strip().upper()),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "jiraKey": row["jira_key"],
        "projectKey": row["project_key"],
        "title": row["title"],
        "readinessStatus": row["readiness_status"],
        "readinessScore": row["readiness_score"],
    }


def latest_estimations_by_readiness(*, project_key: str) -> dict[str, dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT te.*
            FROM ticket_estimations te
            INNER JOIN readiness_records rr ON rr.id = te.readiness_id
            WHERE rr.project_key = ?
            ORDER BY te.created_at DESC, te.id DESC
            """,
            (project_key,),
        ).fetchall()

    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        readiness_id = row["readiness_id"]
        if readiness_id in latest:
            continue
        latest[readiness_id] = _row_to_estimation(row)
    return latest


def upsert_comment_proposal(
    conn,
    *,
    readiness_id: str,
    jira_key: str,
    proposal_type: str,
    body: str,
) -> str:
    existing = conn.execute(
        """
        SELECT id FROM jira_comment_proposals
        WHERE readiness_id = ? AND proposal_type = ? AND status = 'pending'
        """,
        (readiness_id, proposal_type),
    ).fetchone()

    now = utc_now_iso()
    if existing:
        proposal_id = existing["id"]
        conn.execute(
            """
            UPDATE jira_comment_proposals
            SET body = ?, updated_at = ?
            WHERE id = ?
            """,
            (body, now, proposal_id),
        )
        return proposal_id

    proposal_id = next_public_id(conn, "JP")
    conn.execute(
        """
        INSERT INTO jira_comment_proposals (
            id, readiness_id, work_order_id, jira_key, proposal_type, status, body, created_at, updated_at
        ) VALUES (?, ?, NULL, ?, ?, 'pending', ?, ?, ?)
        """,
        (proposal_id, readiness_id, jira_key, proposal_type, body, now, now),
    )
    return proposal_id


def list_pending_proposals(*, project_key: str | None = None) -> list[dict[str, Any]]:
    clauses = ["status = 'pending'"]
    params: list[Any] = []
    if project_key:
        clauses.append(
            """
            (
                readiness_id IN (
                    SELECT id FROM readiness_records WHERE project_key = ?
                )
                OR work_order_id IN (
                    SELECT id FROM work_orders
                )
            )
            """
        )
        params.append(project_key)

    where = " AND ".join(clauses)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM jira_comment_proposals WHERE {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
    return [_row_to_proposal(row) for row in rows]


def get_comment_proposal(proposal_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM jira_comment_proposals WHERE id = ?",
            (proposal_id,),
        ).fetchone()
    return _row_to_proposal(row) if row else None


def update_comment_proposal_status(
    *,
    proposal_id: str,
    status: str,
    body: str | None = None,
    approved_by: str | None = None,
) -> dict[str, Any]:
    now = utc_now_iso()
    with connect() as conn:
        if body is not None:
            conn.execute(
                """
                UPDATE jira_comment_proposals
                SET status = ?, body = ?, updated_at = ?, approved_by = ?
                WHERE id = ?
                """,
                (status, body, now, approved_by, proposal_id),
            )
        else:
            conn.execute(
                """
                UPDATE jira_comment_proposals
                SET status = ?, updated_at = ?, approved_by = ?
                WHERE id = ?
                """,
                (status, now, approved_by, proposal_id),
            )
        row = conn.execute(
            "SELECT * FROM jira_comment_proposals WHERE id = ?",
            (proposal_id,),
        ).fetchone()
    if not row:
        raise LookupError("Comment proposal not found")
    return _row_to_proposal(row)


def upsert_sprint_state(
    conn,
    *,
    project_key: str,
    sprint_name: str,
    capacity_days: float,
    duration_days: int,
    recommendation: dict[str, Any],
    memory_patch: dict[str, Any] | None = None,
) -> str:
    row = conn.execute(
        "SELECT id, memory_json FROM sprint_state WHERE project_key = ?",
        (project_key,),
    ).fetchone()
    now = utc_now_iso()
    memory = json_loads(row["memory_json"], {}) if row else {}
    if memory_patch:
        memory.update(memory_patch)
    memory["lastRecommendationAt"] = now

    if row:
        sprint_id = row["id"]
        conn.execute(
            """
            UPDATE sprint_state
            SET sprint_name = ?, capacity_days = ?, duration_days = ?,
                recommendation_json = ?, memory_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                sprint_name,
                capacity_days,
                duration_days,
                json_dumps(recommendation),
                json_dumps(memory),
                now,
                sprint_id,
            ),
        )
        return sprint_id

    sprint_id = next_public_id(conn, "SP")
    conn.execute(
        """
        INSERT INTO sprint_state (
            id, project_key, sprint_name, capacity_days, duration_days,
            memory_json, recommendation_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sprint_id,
            project_key,
            sprint_name,
            capacity_days,
            duration_days,
            json_dumps(memory),
            json_dumps(recommendation),
            now,
            now,
        ),
    )
    return sprint_id


def get_sprint_state(*, project_key: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM sprint_state WHERE project_key = ?",
            (project_key,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "projectKey": row["project_key"],
        "sprintName": row["sprint_name"],
        "capacityDays": row["capacity_days"],
        "durationDays": row["duration_days"],
        "memory": json_loads(row["memory_json"], {}),
        "recommendation": json_loads(row["recommendation_json"], {}),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def list_new_readiness_since(*, project_key: str, since_iso: str | None) -> list[str]:
    clauses = ["project_key = ?", "readiness_status NOT IN ('promoted', 'dismissed')"]
    params: list[Any] = [project_key]
    if since_iso:
        clauses.append("created_at > ?")
        params.append(since_iso)

    where = " AND ".join(clauses)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT jira_key FROM readiness_records
            WHERE {where}
            ORDER BY created_at DESC
            """,
            params,
        ).fetchall()
    return [str(row["jira_key"]) for row in rows]


def replace_execution_queue(
    conn,
    *,
    project_key: str,
    items: list[dict[str, Any]],
    run_id: str,
) -> None:
    conn.execute("DELETE FROM execution_queue_items WHERE project_key = ?", (project_key,))
    now = utc_now_iso()
    for item in items:
        queue_id = next_public_id(conn, "EQ")
        conn.execute(
            """
            INSERT INTO execution_queue_items (
                id, project_key, readiness_id, jira_key, title, queue_status,
                priority_score, estimated_days, complexity, confidence,
                blockers_json, priority_factors_json, position, recommended_next,
                run_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                queue_id,
                project_key,
                item["readinessId"],
                item["jiraKey"],
                item.get("title") or item["jiraKey"],
                item["queueStatus"],
                item.get("priorityScore") or 0,
                item.get("estimatedDays"),
                item.get("complexity"),
                item.get("confidence"),
                json_dumps(item.get("blockers") or []),
                json_dumps(item.get("priorityFactors") or {}),
                item.get("position") or 0,
                1 if item.get("recommendedNext") else 0,
                run_id,
                now,
            ),
        )


def get_execution_queue(*, project_key: str) -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM execution_queue_items
            WHERE project_key = ?
            ORDER BY position ASC
            """,
            (project_key,),
        ).fetchall()

    items = []
    recommended_next = None
    for row in rows:
        item = {
            "readinessId": row["readiness_id"],
            "jiraKey": row["jira_key"],
            "title": row["title"],
            "queueStatus": row["queue_status"],
            "priorityScore": row["priority_score"],
            "estimatedDays": row["estimated_days"],
            "complexity": row["complexity"],
            "confidence": row["confidence"],
            "blockers": json_loads(row["blockers_json"], []),
            "priorityFactors": json_loads(row["priority_factors_json"], {}),
            "position": row["position"],
            "recommendedNext": bool(row["recommended_next"]),
            "workOrderId": row["work_order_id"] if "work_order_id" in row.keys() else None,
            "startedAt": row["started_at"] if "started_at" in row.keys() else None,
            "failureReason": row["failure_reason"] if "failure_reason" in row.keys() else None,
        }
        items.append(item)
        if item["recommendedNext"]:
            recommended_next = item

    return {
        "projectKey": project_key,
        "recommendedNext": recommended_next,
        "items": items,
        "executableCount": sum(1 for item in items if item["queueStatus"] == "executable"),
        "blockedCount": sum(1 for item in items if item["queueStatus"] not in {"executable", "in_progress"}),
    }


def readiness_has_pending_proposal(*, readiness_id: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM jira_comment_proposals
            WHERE readiness_id = ? AND status = 'pending'
            LIMIT 1
            """,
            (readiness_id,),
        ).fetchone()
    return row is not None


def mark_queue_item_in_progress(
    *,
    project_key: str,
    jira_key: str,
    readiness_id: str,
    started_at: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE execution_queue_items
            SET queue_status = 'in_progress',
                readiness_id = ?,
                started_at = ?,
                failure_reason = NULL,
                updated_at = ?
            WHERE project_key = ? AND jira_key = ?
            """,
            (readiness_id, started_at, utc_now_iso(), project_key, jira_key),
        )


def attach_work_order_to_queue_item(
    *,
    project_key: str,
    jira_key: str,
    work_order_id: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE execution_queue_items
            SET work_order_id = ?, updated_at = ?
            WHERE project_key = ? AND jira_key = ?
            """,
            (work_order_id, utc_now_iso(), project_key, jira_key),
        )


def release_queue_item(
    *,
    project_key: str,
    jira_key: str,
    failure_reason: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    sql = """
            UPDATE execution_queue_items
            SET queue_status = 'executable',
                work_order_id = NULL,
                failure_reason = ?,
                updated_at = ?
            WHERE project_key = ? AND jira_key = ?
            """
    params = (failure_reason, utc_now_iso(), project_key, jira_key)
    if conn is not None:
        conn.execute(sql, params)
        return
    with connect() as owned:
        owned.execute(sql, params)


def upsert_project_memory(
    conn,
    *,
    project_key: str,
    memory: dict[str, Any],
    highlights: list[dict[str, Any]],
) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO project_memory (project_key, memory_json, highlights_json, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(project_key) DO UPDATE SET
            memory_json = excluded.memory_json,
            highlights_json = excluded.highlights_json,
            updated_at = excluded.updated_at
        """,
        (project_key, json_dumps(memory), json_dumps(highlights), now),
    )


def get_project_memory(*, project_key: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM project_memory WHERE project_key = ?",
            (project_key,),
        ).fetchone()
    if not row:
        return None
    return {
        "projectKey": row["project_key"],
        "memory": json_loads(row["memory_json"], {}),
        "highlights": json_loads(row["highlights_json"], []),
        "updatedAt": row["updated_at"],
    }
