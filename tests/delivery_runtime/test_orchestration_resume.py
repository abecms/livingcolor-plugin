"""Tests for work order resume helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from delivery_runtime.execution_graph.scheduler import mark_node_running
from delivery_runtime.orchestration.resume import prepare_work_order_resume
from delivery_runtime.persistence.db import connect, init_db, next_public_id, utc_now_iso


def test_prepare_work_order_resume_unsticks_running_development_node():
    init_db()
    with connect() as conn:
        work_order_id = next_public_id(conn, "WO")
        node_id = next_public_id(conn, "GN")
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO work_orders (
                id, jira_key, title, description, priority, status, current_stage,
                confidence, created_at, updated_at
            ) VALUES (?, 'TVP-1', 'Demo', '', 'Medium', 'running', 'development', 0.5, ?, ?)
            """,
            (work_order_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO graph_nodes (
                id, work_order_id, node_type, status, depends_on_json, payload_json, started_at
            ) VALUES (?, ?, 'development', 'ready', '[]', '{}', NULL)
            """,
            (node_id, work_order_id),
        )
        mark_node_running(conn, node_id)
        conn.execute(
            "UPDATE graph_nodes SET started_at = ? WHERE id = ?",
            ((datetime.now(UTC) - timedelta(minutes=5)).isoformat(), node_id),
        )

        reset_ids = prepare_work_order_resume(conn, work_order_id)
        row = conn.execute("SELECT status FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()

    assert reset_ids == [node_id]
    assert row["status"] == "ready"


def test_prepare_work_order_resume_keeps_recent_running_node():
    init_db()
    with connect() as conn:
        work_order_id = next_public_id(conn, "WO")
        node_id = next_public_id(conn, "GN")
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO work_orders (
                id, jira_key, title, description, priority, status, current_stage,
                confidence, created_at, updated_at
            ) VALUES (?, 'TVP-2', 'Demo', '', 'Medium', 'running', 'development', 0.5, ?, ?)
            """,
            (work_order_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO graph_nodes (
                id, work_order_id, node_type, status, depends_on_json, payload_json, started_at
            ) VALUES (?, ?, 'development', 'ready', '[]', '{}', NULL)
            """,
            (node_id, work_order_id),
        )
        mark_node_running(conn, node_id)

        reset_ids = prepare_work_order_resume(conn, work_order_id)
        row = conn.execute("SELECT status FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()

    assert reset_ids == []
    assert row["status"] == "running"
