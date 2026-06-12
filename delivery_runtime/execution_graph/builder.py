"""Execution graph construction for Work Orders."""

from __future__ import annotations

import sqlite3
from typing import Any

from delivery_runtime.persistence.db import json_dumps, next_public_id

DEFAULT_GRAPH: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("implementation_plan", ()),
    ("development", ("implementation_plan",)),
    ("qa_validation", ("development",)),
    ("mr_creation", ("qa_validation",)),
    ("jira_update", ("mr_creation",)),
)


def build_default_graph(conn: sqlite3.Connection, work_order_id: str) -> list[dict[str, Any]]:
    """Instantiate the MVP sequential graph for a new Work Order."""
    node_ids_by_type: dict[str, str] = {}
    created_nodes: list[dict[str, Any]] = []

    for node_type, dependency_types in DEFAULT_GRAPH:
        node_id = next_public_id(conn, "GN")
        depends_on = [node_ids_by_type[dep] for dep in dependency_types if dep in node_ids_by_type]
        initial_status = "ready" if not depends_on else "pending"
        conn.execute(
            """
            INSERT INTO graph_nodes (
                id, work_order_id, node_type, status, depends_on_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, '{}')
            """,
            (node_id, work_order_id, node_type, initial_status, json_dumps(depends_on)),
        )
        node_ids_by_type[node_type] = node_id
        created_nodes.append(
            {
                "id": node_id,
                "nodeType": node_type,
                "dependsOn": depends_on,
            }
        )

    return created_nodes
