"""Tests for Delivery Runtime persistence."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from delivery_runtime.events.store import EventStore
from delivery_runtime.persistence.db import SCHEMA_VERSION, connect, init_db, next_public_id


def test_init_db_creates_schema(_isolate_hermes_home):
    path = init_db()
    assert path.exists()

    with connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    assert "readiness_records" in tables
    assert "work_orders" in tables
    assert "graph_nodes" in tables
    assert "gates" in tables
    assert "events" in tables


def test_readiness_records_include_analysis_metadata_columns(_isolate_hermes_home):
    init_db()

    with connect() as conn:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(readiness_records)").fetchall()
        }
        version = conn.execute(
            "SELECT value FROM delivery_meta WHERE key = 'schema_version'"
        ).fetchone()["value"]

    assert int(version) == SCHEMA_VERSION
    assert "analysis_input_hash" in columns
    assert "analysis_backend" in columns
    assert "last_analysis_error" in columns
    assert "last_analysis_failed_at" in columns


def test_next_public_id_increments(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        first = next_public_id(conn, "WO")
        second = next_public_id(conn, "WO")
    assert first == "WO-1"
    assert second == "WO-2"


def test_init_db_upgrades_legacy_schema_v2(tmp_path: Path):
    db_path = tmp_path / "runtime.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE delivery_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT INTO delivery_meta(key, value) VALUES ('schema_version', '2');
            CREATE TABLE work_orders (
                id TEXT PRIMARY KEY,
                jira_key TEXT NOT NULL,
                readiness_id TEXT,
                title TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'intake',
                current_stage TEXT NOT NULL DEFAULT 'intake',
                confidence REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    init_db(db_path)

    with connect(db_path) as upgraded:
        version = upgraded.execute(
            "SELECT value FROM delivery_meta WHERE key = 'schema_version'"
        ).fetchone()["value"]
        tables = {
            row["name"]
            for row in upgraded.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert int(version) == SCHEMA_VERSION
    assert "merge_request_drafts" in tables


def test_connect_handles_concurrent_readers(_isolate_hermes_home):
    init_db()

    def read_count() -> int:
        with connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM events").fetchone()
            return int(row["count"])

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: read_count(), range(16)))

    assert all(result == 0 for result in results)


def test_connect_handles_concurrent_writers(_isolate_hermes_home):
    init_db()
    store = EventStore()

    def append_event(index: int) -> str:
        created = store.append(
            event_type="READINESS_SCAN_STARTED",
            actor="system",
            payload={"index": index},
        )
        return created["id"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        event_ids = list(pool.map(append_event, range(16)))

    assert len(set(event_ids)) == 16


def test_event_store_is_append_only(_isolate_hermes_home):
    init_db()
    store = EventStore()
    created = store.append(
        event_type="READINESS_SCAN_STARTED",
        actor="system",
        payload={"projectKey": "AAC"},
    )
    recent = store.list_recent(limit=5)
    assert recent[0]["id"] == created["id"]
    assert recent[0]["eventType"] == "READINESS_SCAN_STARTED"
    assert recent[0]["payload"]["projectKey"] == "AAC"
