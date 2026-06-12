"""Work order resume helpers — unstick orchestrator state."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from delivery_runtime.execution_graph.scheduler import reset_node_for_retry
from delivery_runtime.orchestration.engine import PHASE3A_EXECUTABLE_NODES
from delivery_runtime.persistence.db import json_loads

_STUCK_RUNNING_SECONDS = 90


def prepare_work_order_resume(conn: sqlite3.Connection, work_order_id: str) -> list[str]:
    """Reset executable nodes stuck in ``running`` so the orchestrator can retry them.

    Nodes that started recently are left alone — a resume click must not interrupt
    an orchestrator tick that is already executing the developer agent.
    """
    rows = conn.execute(
        """
        SELECT id, node_type, payload_json, started_at
        FROM graph_nodes
        WHERE work_order_id = ? AND status = 'running'
        ORDER BY rowid ASC
        """,
        (work_order_id,),
    ).fetchall()

    reset_ids: list[str] = []
    for row in rows:
        node_type = str(row["node_type"])
        if node_type not in PHASE3A_EXECUTABLE_NODES:
            continue
        if not _is_stuck_running(row["started_at"]):
            continue
        node_id = str(row["id"])
        payload = json_loads(row["payload_json"], {})
        reset_node_for_retry(conn, node_id, payload=payload)
        reset_ids.append(node_id)
    return reset_ids


def _is_stuck_running(started_at: str | None) -> bool:
    if not started_at:
        return True
    try:
        started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return datetime.now(UTC) - started > timedelta(seconds=_STUCK_RUNNING_SECONDS)
