from __future__ import annotations

from delivery_runtime.persistence.db import connect, init_db
from delivery_runtime.persistence.pending_events import (
    enqueue_pending_event,
    list_pending_events,
    mark_pending_events_flushed,
)


def test_enqueue_and_flush_pending_events(tmp_path, monkeypatch):
    db_path = tmp_path / "runtime.db"
    monkeypatch.setattr("delivery_runtime.persistence.db.get_delivery_db_path", lambda: db_path)
    init_db(db_path)

    event_id = enqueue_pending_event(
        org_id="org1",
        wo_id="WO-1",
        payload={"type": "state_change", "updatedAt": "2026-06-12T10:00:00Z"},
    )

    pending = list_pending_events("org1")
    assert len(pending) == 1
    assert pending[0]["id"] == event_id
    assert pending[0]["woId"] == "WO-1"

    flushed = mark_pending_events_flushed([event_id])
    assert flushed == 1
    assert list_pending_events("org1") == []

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT flushed_at FROM pending_cloud_events WHERE id = ?",
            (event_id,),
        ).fetchone()
    assert row["flushed_at"]
