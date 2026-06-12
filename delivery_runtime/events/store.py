"""Append-only event store for Delivery Runtime audit trail."""

from __future__ import annotations

import sqlite3
from typing import Any

from delivery_runtime.persistence.db import connect, json_dumps, next_public_id, utc_now_iso


class EventStore:
    def append(
        self,
        *,
        event_type: str,
        actor: str = "system",
        work_order_id: str | None = None,
        readiness_id: str | None = None,
        payload: dict[str, Any] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        record = {
            "event_type": event_type,
            "actor": actor,
            "work_order_id": work_order_id,
            "readiness_id": readiness_id,
            "payload": payload or {},
            "created_at": utc_now_iso(),
        }

        if conn is not None:
            record["id"] = self._insert(conn, record)
            return record

        with connect() as owned:
            record["id"] = self._insert(owned, record)
        return record

    def list_for_work_order(
        self,
        work_order_id: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT id, work_order_id, readiness_id, event_type, payload_json,
                       actor, created_at
                FROM events
                WHERE work_order_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (work_order_id, limit),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def list_recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT id, work_order_id, readiness_id, event_type, payload_json,
                       actor, created_at
                FROM events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def _insert(self, conn: sqlite3.Connection, record: dict[str, Any]) -> str:
        event_id = next_public_id(conn, "EV")
        conn.execute(
            """
            INSERT INTO events (
                id, work_order_id, readiness_id, event_type, payload_json, actor, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                record["work_order_id"],
                record["readiness_id"],
                record["event_type"],
                json_dumps(record["payload"]),
                record["actor"],
                record["created_at"],
            ),
        )
        return event_id

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        import json

        return {
            "id": row["id"],
            "workOrderId": row["work_order_id"],
            "readinessId": row["readiness_id"],
            "eventType": row["event_type"],
            "payload": json.loads(row["payload_json"] or "{}"),
            "actor": row["actor"],
            "createdAt": row["created_at"],
        }
