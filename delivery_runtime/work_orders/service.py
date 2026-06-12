"""Work Order service."""

from __future__ import annotations

import sqlite3
from typing import Any

from delivery_runtime.events.store import EventStore
from delivery_runtime.execution_graph.builder import build_default_graph
from delivery_runtime.persistence.db import connect, json_dumps, json_loads, next_public_id, utc_now_iso


class WorkOrderService:
    def __init__(self, events: EventStore | None = None) -> None:
        self.events = events or EventStore()

    def list_work_orders(
        self,
        *,
        stage: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = ["1=1"]
        params: list[Any] = []

        if stage:
            clauses.append("current_stage = ?")
            params.append(stage)
        if status:
            clauses.append("status = ?")
            params.append(status)

        where = " AND ".join(clauses)
        with connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM work_orders
                WHERE {where}
                ORDER BY updated_at DESC
                """,
                params,
            ).fetchall()
            return [
                {
                    **self._row_to_dict(row),
                    "gates": self._list_gates(conn, row["id"]),
                }
                for row in rows
            ]

    def get_work_order(self, work_order_id: str) -> dict[str, Any] | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM work_orders WHERE id = ?",
                (work_order_id,),
            ).fetchone()
            if not row:
                return None
            detail = self._row_to_dict(row)
            detail["graphNodes"] = self._list_graph_nodes(conn, work_order_id)
            detail["gates"] = self._list_gates(conn, work_order_id)
        return detail

    def create_from_readiness(
        self,
        readiness: dict[str, Any],
        *,
        actor: str = "human",
    ) -> dict[str, Any]:
        readiness_id = readiness["id"]
        jira_key = readiness["jiraKey"]
        snapshot = readiness.get("jiraSnapshot") or {}
        description = str(snapshot.get("description") or readiness.get("analysisSummary") or "")
        priority = str(snapshot.get("priority") or "")

        with connect() as conn:
            existing = conn.execute(
                """
                SELECT id FROM work_orders
                WHERE jira_key = ? AND status NOT IN ('completed', 'cancelled', 'failed')
                """,
                (jira_key,),
            ).fetchone()
            if existing:
                raise ValueError(f"An active work order already exists for {jira_key}")

            now = utc_now_iso()
            work_order_id = next_public_id(conn, "WO")
            conn.execute(
                """
                INSERT INTO work_orders (
                    id, jira_key, readiness_id, title, description, priority,
                    status, current_stage, confidence, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'intake', 'intake', ?, ?, ?)
                """,
                (
                    work_order_id,
                    jira_key,
                    readiness_id,
                    readiness.get("title") or jira_key,
                    description,
                    priority,
                    readiness.get("confidence") or 0,
                    now,
                    now,
                ),
            )
            build_default_graph(conn, work_order_id)
            conn.execute(
                """
                UPDATE readiness_records
                SET readiness_status = 'promoted',
                    promoted_work_order_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (work_order_id, now, readiness_id),
            )

            self.events.append(
                event_type="WORK_ORDER_CREATED",
                work_order_id=work_order_id,
                readiness_id=readiness_id,
                actor=actor,
                payload={"jiraKey": jira_key},
                conn=conn,
            )
            self.events.append(
                event_type="READINESS_PROMOTED_TO_WORK_ORDER",
                work_order_id=work_order_id,
                readiness_id=readiness_id,
                actor=actor,
                payload={"jiraKey": jira_key},
                conn=conn,
            )

        created = self.get_work_order(work_order_id)
        if not created:
            raise RuntimeError("Work order creation failed")
        return created

    @staticmethod
    def _list_graph_nodes(conn: sqlite3.Connection, work_order_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT id, work_order_id, node_type, status, depends_on_json,
                   agent_profile, payload_json, started_at, completed_at
            FROM graph_nodes
            WHERE work_order_id = ?
            ORDER BY rowid ASC
            """,
            (work_order_id,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "workOrderId": row["work_order_id"],
                "nodeType": row["node_type"],
                "status": row["status"],
                "dependsOn": json_loads(row["depends_on_json"], []),
                "agentProfile": row["agent_profile"],
                "payload": json_loads(row["payload_json"], {}),
                "startedAt": row["started_at"],
                "completedAt": row["completed_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _list_gates(conn: sqlite3.Connection, work_order_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT id, work_order_id, gate_type, status, payload_json,
                   created_at, approved_at, approved_by, rejection_feedback
            FROM gates
            WHERE work_order_id = ?
            ORDER BY created_at ASC
            """,
            (work_order_id,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "workOrderId": row["work_order_id"],
                "gateType": row["gate_type"],
                "status": row["status"],
                "payload": json_loads(row["payload_json"], {}),
                "createdAt": row["created_at"],
                "approvedAt": row["approved_at"],
                "approvedBy": row["approved_by"],
                "rejectionFeedback": row["rejection_feedback"],
            }
            for row in rows
        ]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "jiraKey": row["jira_key"],
            "readinessId": row["readiness_id"],
            "title": row["title"],
            "description": row["description"],
            "priority": row["priority"],
            "status": row["status"],
            "currentStage": row["current_stage"],
            "confidence": row["confidence"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
