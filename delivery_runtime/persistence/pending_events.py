"""SQLite queue for offline cloud event flush."""

from __future__ import annotations

from typing import Any

from delivery_runtime.persistence.db import connect, json_dumps, json_loads, utc_now_iso


def enqueue_pending_event(org_id: str, wo_id: str, payload: dict[str, Any]) -> int:
    org = org_id.strip()
    work_order_id = wo_id.strip()
    if not org:
        raise ValueError("org_id is required")
    if not work_order_id:
        raise ValueError("wo_id is required")
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO pending_cloud_events (org_id, wo_id, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (org, work_order_id, json_dumps(payload), utc_now_iso()),
        )
        return int(cursor.lastrowid)


def list_pending_events(org_id: str) -> list[dict[str, Any]]:
    org = org_id.strip()
    if not org:
        return []
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, org_id, wo_id, payload_json, created_at
            FROM pending_cloud_events
            WHERE org_id = ? AND flushed_at IS NULL
            ORDER BY id ASC
            """,
            (org,),
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "orgId": row["org_id"],
            "woId": row["wo_id"],
            "payload": json_loads(row["payload_json"], {}),
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


def mark_pending_events_flushed(event_ids: list[int]) -> int:
    cleaned = [int(event_id) for event_id in event_ids if int(event_id) > 0]
    if not cleaned:
        return 0
    now = utc_now_iso()
    placeholders = ", ".join("?" for _ in cleaned)
    with connect() as conn:
        cursor = conn.execute(
            f"""
            UPDATE pending_cloud_events
            SET flushed_at = ?
            WHERE id IN ({placeholders}) AND flushed_at IS NULL
            """,
            [now, *cleaned],
        )
        return int(cursor.rowcount)
