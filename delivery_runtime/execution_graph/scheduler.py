"""Execution graph node readiness helpers."""

from __future__ import annotations

import sqlite3
from typing import Any

from delivery_runtime.persistence.db import json_loads, utc_now_iso


def _fetch_nodes(conn: sqlite3.Connection, work_order_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, node_type, status, depends_on_json, payload_json
        FROM graph_nodes
        WHERE work_order_id = ?
        ORDER BY rowid ASC
        """,
        (work_order_id,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "nodeType": row["node_type"],
            "status": row["status"],
            "dependsOn": json_loads(row["depends_on_json"], []),
            "payload": json_loads(row["payload_json"], {}),
        }
        for row in rows
    ]


def refresh_node_readiness(conn: sqlite3.Connection, work_order_id: str) -> list[str]:
    """Promote pending nodes to ready when all dependencies are completed."""
    nodes = _fetch_nodes(conn, work_order_id)
    by_id = {node["id"]: node for node in nodes}
    promoted: list[str] = []

    for node in nodes:
        if node["status"] != "pending":
            continue
        deps = node["dependsOn"]
        if deps and not all(by_id.get(dep_id, {}).get("status") == "completed" for dep_id in deps):
            continue
        conn.execute(
            "UPDATE graph_nodes SET status = 'ready' WHERE id = ? AND status = 'pending'",
            (node["id"],),
        )
        if conn.total_changes:
            promoted.append(node["id"])
    return promoted


def find_ready_nodes(
    conn: sqlite3.Connection,
    work_order_id: str,
    *,
    node_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    refresh_node_readiness(conn, work_order_id)
    nodes = _fetch_nodes(conn, work_order_id)
    ready = [node for node in nodes if node["status"] == "ready"]
    if node_types is not None:
        ready = [node for node in ready if node["nodeType"] in node_types]
    return ready


def has_pending_gate(conn: sqlite3.Connection, work_order_id: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM gates
        WHERE work_order_id = ? AND status = 'pending'
        LIMIT 1
        """,
        (work_order_id,),
    ).fetchone()
    return row is not None


def mark_node_running(conn: sqlite3.Connection, node_id: str) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE graph_nodes
        SET status = 'running', started_at = ?, completed_at = NULL
        WHERE id = ? AND status = 'ready'
        """,
        (now, node_id),
    )


def mark_node_completed(conn: sqlite3.Connection, node_id: str, payload: dict[str, Any]) -> None:
    from delivery_runtime.persistence.db import json_dumps

    now = utc_now_iso()
    conn.execute(
        """
        UPDATE graph_nodes
        SET status = 'completed', payload_json = ?, completed_at = ?
        WHERE id = ?
        """,
        (json_dumps(payload), now, node_id),
    )


def reset_node_for_retry(
    conn: sqlite3.Connection,
    node_id: str,
    *,
    payload: dict[str, Any],
) -> None:
    from delivery_runtime.persistence.db import json_dumps

    conn.execute(
        """
        UPDATE graph_nodes
        SET status = 'ready',
            payload_json = ?,
            started_at = NULL,
            completed_at = NULL
        WHERE id = ?
        """,
        (json_dumps(payload), node_id),
    )
