"""SQLite persistence for Delivery Runtime."""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from delivery_runtime.persistence.paths import (
    get_delivery_db_path,
    get_delivery_root,
    get_project_mapping_path,
)

SCHEMA_VERSION = 12

LOCAL_ORG_ID = "local"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS delivery_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS id_counters (
    prefix TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS readiness_records (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT 'local',
    jira_key TEXT NOT NULL,
    project_key TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    readiness_score INTEGER NOT NULL DEFAULT 0,
    readiness_status TEXT NOT NULL DEFAULT 'pending_analysis',
    analysis_summary TEXT NOT NULL DEFAULT '',
    blockers_json TEXT NOT NULL DEFAULT '[]',
    recommended_repos_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0,
    estimated_days REAL,
    analysis_input_hash TEXT,
    analysis_backend TEXT,
    last_analysis_error TEXT,
    last_analysis_failed_at TEXT,
    jira_snapshot_json TEXT NOT NULL DEFAULT '{}',
    analyzed_at TEXT,
    promoted_work_order_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_readiness_jira_active
    ON readiness_records(jira_key)
    WHERE readiness_status NOT IN ('promoted', 'dismissed');

CREATE TABLE IF NOT EXISTS work_orders (
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

CREATE TABLE IF NOT EXISTS graph_nodes (
    id TEXT PRIMARY KEY,
    work_order_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    depends_on_json TEXT NOT NULL DEFAULT '[]',
    agent_profile TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT,
    completed_at TEXT,
    FOREIGN KEY (work_order_id) REFERENCES work_orders(id)
);

CREATE INDEX IF NOT EXISTS idx_graph_nodes_work_order
    ON graph_nodes(work_order_id);

CREATE TABLE IF NOT EXISTS gates (
    id TEXT PRIMARY KEY,
    work_order_id TEXT NOT NULL,
    gate_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    approved_at TEXT,
    approved_by TEXT,
    rejection_feedback TEXT,
    FOREIGN KEY (work_order_id) REFERENCES work_orders(id)
);

CREATE INDEX IF NOT EXISTS idx_gates_work_order
    ON gates(work_order_id);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    work_order_id TEXT,
    readiness_id TEXT,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    actor TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_work_order
    ON events(work_order_id, created_at);

CREATE INDEX IF NOT EXISTS idx_events_readiness
    ON events(readiness_id, created_at);

CREATE TABLE IF NOT EXISTS scope_contracts (
    id TEXT PRIMARY KEY,
    work_order_id TEXT NOT NULL UNIQUE,
    allowed_files_json TEXT NOT NULL DEFAULT '[]',
    allowed_directories_json TEXT NOT NULL DEFAULT '[]',
    forbidden_paths_json TEXT NOT NULL DEFAULT '[]',
    max_files_touched INTEGER NOT NULL DEFAULT 5,
    max_lines_changed INTEGER NOT NULL DEFAULT 200,
    created_at TEXT NOT NULL,
    FOREIGN KEY (work_order_id) REFERENCES work_orders(id)
);

CREATE INDEX IF NOT EXISTS idx_scope_contracts_work_order
    ON scope_contracts(work_order_id);

CREATE TABLE IF NOT EXISTS merge_request_drafts (
    id TEXT PRIMARY KEY,
    work_order_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    ticket_summary TEXT NOT NULL DEFAULT '',
    implementation_summary TEXT NOT NULL DEFAULT '',
    files_modified_json TEXT NOT NULL DEFAULT '[]',
    risks_json TEXT NOT NULL DEFAULT '[]',
    reviewers_json TEXT NOT NULL DEFAULT '[]',
    qa_checklist_json TEXT NOT NULL DEFAULT '{}',
    decision_trace_json TEXT NOT NULL DEFAULT '{}',
    mr_url TEXT NOT NULL DEFAULT '',
    mr_iid INTEGER,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (work_order_id) REFERENCES work_orders(id)
);

CREATE INDEX IF NOT EXISTS idx_mr_drafts_work_order
    ON merge_request_drafts(work_order_id);

CREATE TABLE IF NOT EXISTS daily_analysis_runs (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT 'local',
    project_key TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    jira_synced INTEGER NOT NULL DEFAULT 0,
    analyzed INTEGER NOT NULL DEFAULT 0,
    estimated INTEGER NOT NULL DEFAULT 0,
    pipeline_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_daily_runs_org_project_started
    ON daily_analysis_runs(org_id, project_key, started_at DESC);

CREATE TABLE IF NOT EXISTS ticket_estimations (
    id TEXT PRIMARY KEY,
    readiness_id TEXT NOT NULL,
    jira_key TEXT NOT NULL,
    complexity TEXT NOT NULL,
    estimated_days REAL NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    run_id TEXT,
    FOREIGN KEY (readiness_id) REFERENCES readiness_records(id)
);

CREATE INDEX IF NOT EXISTS idx_ticket_estimations_readiness
    ON ticket_estimations(readiness_id, created_at DESC);

CREATE TABLE IF NOT EXISTS jira_comment_proposals (
    id TEXT PRIMARY KEY,
    readiness_id TEXT,
    work_order_id TEXT,
    jira_key TEXT NOT NULL,
    proposal_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_by TEXT,
    published_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_comment_proposals_status
    ON jira_comment_proposals(status, created_at DESC);

CREATE TABLE IF NOT EXISTS sprint_state (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT 'local',
    project_key TEXT NOT NULL,
    sprint_name TEXT NOT NULL,
    capacity_days REAL NOT NULL DEFAULT 15,
    duration_days INTEGER NOT NULL DEFAULT 14,
    memory_json TEXT NOT NULL DEFAULT '{}',
    recommendation_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sprint_state_org_project
    ON sprint_state(org_id, project_key);

CREATE TABLE IF NOT EXISTS pending_cloud_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id TEXT NOT NULL,
    wo_id TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    flushed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_pending_cloud_events_org_pending
    ON pending_cloud_events(org_id, flushed_at, id);
"""

_SCHEMA_V5_SQL = """
CREATE TABLE IF NOT EXISTS daily_analysis_runs (
    id TEXT PRIMARY KEY,
    project_key TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    jira_synced INTEGER NOT NULL DEFAULT 0,
    analyzed INTEGER NOT NULL DEFAULT 0,
    estimated INTEGER NOT NULL DEFAULT 0,
    pipeline_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_daily_runs_project_started
    ON daily_analysis_runs(project_key, started_at DESC);

CREATE TABLE IF NOT EXISTS ticket_estimations (
    id TEXT PRIMARY KEY,
    readiness_id TEXT NOT NULL,
    jira_key TEXT NOT NULL,
    complexity TEXT NOT NULL,
    estimated_days REAL NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    run_id TEXT,
    FOREIGN KEY (readiness_id) REFERENCES readiness_records(id)
);

CREATE INDEX IF NOT EXISTS idx_ticket_estimations_readiness
    ON ticket_estimations(readiness_id, created_at DESC);

CREATE TABLE IF NOT EXISTS jira_comment_proposals (
    id TEXT PRIMARY KEY,
    readiness_id TEXT,
    work_order_id TEXT,
    jira_key TEXT NOT NULL,
    proposal_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_by TEXT,
    published_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_comment_proposals_status
    ON jira_comment_proposals(status, created_at DESC);

CREATE TABLE IF NOT EXISTS sprint_state (
    id TEXT PRIMARY KEY,
    project_key TEXT NOT NULL UNIQUE,
    sprint_name TEXT NOT NULL,
    capacity_days REAL NOT NULL DEFAULT 15,
    duration_days INTEGER NOT NULL DEFAULT 14,
    memory_json TEXT NOT NULL DEFAULT '{}',
    recommendation_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_queue_items (
    id TEXT PRIMARY KEY,
    project_key TEXT NOT NULL,
    readiness_id TEXT NOT NULL,
    jira_key TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    queue_status TEXT NOT NULL,
    priority_score REAL NOT NULL DEFAULT 0,
    estimated_days REAL,
    complexity TEXT,
    confidence REAL,
    blockers_json TEXT NOT NULL DEFAULT '[]',
    priority_factors_json TEXT NOT NULL DEFAULT '{}',
    position INTEGER NOT NULL DEFAULT 0,
    recommended_next INTEGER NOT NULL DEFAULT 0,
    run_id TEXT,
    work_order_id TEXT,
    started_at TEXT,
    failure_reason TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(project_key, jira_key)
);

CREATE INDEX IF NOT EXISTS idx_execution_queue_project_position
    ON execution_queue_items(project_key, position ASC);

CREATE TABLE IF NOT EXISTS project_memory (
    project_key TEXT PRIMARY KEY,
    memory_json TEXT NOT NULL DEFAULT '{}',
    highlights_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);
"""

_SCHEMA_V11_SQL = """
CREATE TABLE IF NOT EXISTS pending_cloud_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id TEXT NOT NULL,
    wo_id TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    flushed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_pending_cloud_events_org_pending
    ON pending_cloud_events(org_id, flushed_at, id);
"""

_SCHEMA_V6_SQL = """
CREATE TABLE IF NOT EXISTS execution_queue_items (
    id TEXT PRIMARY KEY,
    project_key TEXT NOT NULL,
    readiness_id TEXT NOT NULL,
    jira_key TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    queue_status TEXT NOT NULL,
    priority_score REAL NOT NULL DEFAULT 0,
    estimated_days REAL,
    complexity TEXT,
    confidence REAL,
    blockers_json TEXT NOT NULL DEFAULT '[]',
    priority_factors_json TEXT NOT NULL DEFAULT '{}',
    position INTEGER NOT NULL DEFAULT 0,
    recommended_next INTEGER NOT NULL DEFAULT 0,
    run_id TEXT,
    work_order_id TEXT,
    started_at TEXT,
    failure_reason TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(project_key, jira_key)
);

CREATE INDEX IF NOT EXISTS idx_execution_queue_project_position
    ON execution_queue_items(project_key, position ASC);

CREATE TABLE IF NOT EXISTS project_memory (
    project_key TEXT PRIMARY KEY,
    memory_json TEXT NOT NULL DEFAULT '{}',
    highlights_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);
"""

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None


_ORG_SCOPED_TABLES = (
    "readiness_records",
    "daily_analysis_runs",
    "sprint_state",
    "execution_queue_items",
    "project_memory",
)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(item["name"])
        for item in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _migrate_org_id_columns(conn: sqlite3.Connection) -> None:
    """Add org_id to project-scoped tables (default local org for legacy rows)."""
    tables = {
        str(item["name"])
        for item in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    for table in _ORG_SCOPED_TABLES:
        if table not in tables:
            continue
        columns = _table_columns(conn, table)
        if "org_id" not in columns:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN org_id TEXT NOT NULL DEFAULT '{LOCAL_ORG_ID}'"
            )

    if "sprint_state" in tables:
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sprint_state_org_project
                ON sprint_state(org_id, project_key)
            """
        )
    if "execution_queue_items" in tables:
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_queue_org_project_jira
                ON execution_queue_items(org_id, project_key, jira_key)
            """
        )
    if "project_memory" in tables:
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_project_memory_org_project
                ON project_memory(org_id, project_key)
            """
        )
    if "daily_analysis_runs" in tables:
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daily_runs_org_project_started
                ON daily_analysis_runs(org_id, project_key, started_at DESC)
            """
        )


def _migrate_execution_queue_consumer_columns(conn: sqlite3.Connection) -> None:
    columns = {
        str(item["name"])
        for item in conn.execute("PRAGMA table_info(execution_queue_items)").fetchall()
    }
    if "work_order_id" not in columns:
        conn.execute("ALTER TABLE execution_queue_items ADD COLUMN work_order_id TEXT")
    if "started_at" not in columns:
        conn.execute("ALTER TABLE execution_queue_items ADD COLUMN started_at TEXT")
    if "failure_reason" not in columns:
        conn.execute("ALTER TABLE execution_queue_items ADD COLUMN failure_reason TEXT")


def _migrate_analysis_metadata_columns(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "readiness_records")
    if "analysis_input_hash" not in columns:
        conn.execute("ALTER TABLE readiness_records ADD COLUMN analysis_input_hash TEXT")
    if "analysis_backend" not in columns:
        conn.execute("ALTER TABLE readiness_records ADD COLUMN analysis_backend TEXT")
    if "last_analysis_error" not in columns:
        conn.execute("ALTER TABLE readiness_records ADD COLUMN last_analysis_error TEXT")
    if "last_analysis_failed_at" not in columns:
        conn.execute("ALTER TABLE readiness_records ADD COLUMN last_analysis_failed_at TEXT")


_MR_DRAFTS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS merge_request_drafts (
    id TEXT PRIMARY KEY,
    work_order_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    ticket_summary TEXT NOT NULL DEFAULT '',
    implementation_summary TEXT NOT NULL DEFAULT '',
    files_modified_json TEXT NOT NULL DEFAULT '[]',
    risks_json TEXT NOT NULL DEFAULT '[]',
    reviewers_json TEXT NOT NULL DEFAULT '[]',
    qa_checklist_json TEXT NOT NULL DEFAULT '{}',
    decision_trace_json TEXT NOT NULL DEFAULT '{}',
    mr_url TEXT NOT NULL DEFAULT '',
    mr_iid INTEGER,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (work_order_id) REFERENCES work_orders(id)
);

CREATE INDEX IF NOT EXISTS idx_mr_drafts_work_order
    ON merge_request_drafts(work_order_id);
"""

_init_lock = threading.Lock()
_initialized_paths: set[str] = set()
_BUSY_TIMEOUT_MS = 5_000
_MIGRATION_BUSY_TIMEOUT_MS = 30_000
_MIGRATION_ATTEMPTS = 8


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    return json.loads(raw)


def _migrate_legacy_storage() -> None:
    """Copy legacy Hermes-era delivery files into ~/.livingcolor/ once."""
    target_db = get_delivery_db_path()
    if not target_db.exists():
        legacy_db = Path.home() / ".hermes" / "delivery" / "delivery.db"
        if legacy_db.exists():
            target_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy_db, target_db)

    target_mapping = get_project_mapping_path()
    if not target_mapping.exists():
        legacy_candidates = (
            Path.home() / ".hermes" / "delivery" / "project_mapping.yaml",
            Path.home() / ".hermes" / "project_mapping.yaml",
        )
        for legacy_mapping in legacy_candidates:
            if legacy_mapping.exists():
                shutil.copy2(legacy_mapping, target_mapping)
                break


def _write_schema_version(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO delivery_meta(key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (str(SCHEMA_VERSION),),
    )


def _apply_schema_migrations(conn: sqlite3.Connection) -> None:
    tables = {
        str(item["name"])
        for item in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "delivery_meta" in tables:
        row = conn.execute(
            "SELECT value FROM delivery_meta WHERE key = 'schema_version'"
        ).fetchone()
        current = int(row["value"]) if row else 0
    else:
        current = 0
    if current >= SCHEMA_VERSION:
        return
    if "merge_request_drafts" in tables:
        columns = {
            str(item["name"])
            for item in conn.execute("PRAGMA table_info(merge_request_drafts)").fetchall()
        }
        if "decision_trace_json" not in columns:
            conn.execute(
                """
                ALTER TABLE merge_request_drafts
                ADD COLUMN decision_trace_json TEXT NOT NULL DEFAULT '{}'
                """
            )
        if "mr_url" not in columns:
            conn.execute(
                "ALTER TABLE merge_request_drafts ADD COLUMN mr_url TEXT NOT NULL DEFAULT ''"
            )
        if "mr_iid" not in columns:
            conn.execute("ALTER TABLE merge_request_drafts ADD COLUMN mr_iid INTEGER")

    if "readiness_records" in tables:
        columns = _table_columns(conn, "readiness_records")
        if "estimated_days" not in columns:
            conn.execute("ALTER TABLE readiness_records ADD COLUMN estimated_days REAL")

    if "readiness_records" in tables:
        _migrate_analysis_metadata_columns(conn)

    if current < 5:
        conn.executescript(_SCHEMA_V5_SQL)

    if current < 6:
        conn.executescript(_SCHEMA_V6_SQL)

    if current < 7:
        _migrate_execution_queue_consumer_columns(conn)

    if current < 8:
        _migrate_org_id_columns(conn)

    if current < 11:
        conn.executescript(_SCHEMA_V11_SQL)


def _configure_connection(conn: sqlite3.Connection, *, busy_timeout_ms: int = _BUSY_TIMEOUT_MS) -> None:
    conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
    conn.execute("PRAGMA foreign_keys=ON")


@contextmanager
def _cross_process_migration_lock(path: Path) -> Iterator[None]:
    """Serialize schema upgrades across dashboard processes."""
    if fcntl is None:
        yield
        return

    lock_path = path.parent / ".runtime.db.init.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _database_exists(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _upgrade_existing_schema(conn: sqlite3.Connection) -> None:
    """Apply incremental DDL for an already-provisioned delivery database."""
    tables = {
        str(item["name"])
        for item in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "delivery_meta" not in tables:
        conn.execute("PRAGMA journal_mode=WAL")
        _configure_connection(conn, busy_timeout_ms=_MIGRATION_BUSY_TIMEOUT_MS)
        conn.executescript(_SCHEMA_SQL)
        tables = {
            str(item["name"])
            for item in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    if "merge_request_drafts" not in tables:
        conn.executescript(_MR_DRAFTS_SCHEMA_SQL)
    _apply_schema_migrations(conn)
    _write_schema_version(conn)
    conn.commit()


def _bootstrap_fresh_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    _configure_connection(conn, busy_timeout_ms=_MIGRATION_BUSY_TIMEOUT_MS)
    conn.executescript(_SCHEMA_SQL)
    _apply_schema_migrations(conn)
    _write_schema_version(conn)
    conn.commit()


def _run_with_migration_retries(path: Path, operation: str) -> None:
    last_error: sqlite3.OperationalError | None = None
    for attempt in range(_MIGRATION_ATTEMPTS):
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            if operation == "upgrade":
                _configure_connection(conn, busy_timeout_ms=_MIGRATION_BUSY_TIMEOUT_MS)
                conn.execute("PRAGMA journal_mode=WAL")
                _upgrade_existing_schema(conn)
            else:
                _bootstrap_fresh_schema(conn)
            last_error = None
            break
        except sqlite3.OperationalError as exc:
            last_error = exc
            if "locked" not in str(exc).lower() or attempt == _MIGRATION_ATTEMPTS - 1:
                raise
            time.sleep(0.1 * (attempt + 1))
        finally:
            conn.close()
    if last_error is not None:
        raise last_error


def _read_schema_version(path: Path) -> int | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        row = conn.execute(
            "SELECT value FROM delivery_meta WHERE key = 'schema_version'"
        ).fetchone()
        if not row:
            return None
        return int(row[0])
    except (sqlite3.Error, TypeError, ValueError):
        return None
    finally:
        conn.close()


def _schema_ready(path: Path) -> bool:
    """Return True when the on-disk schema matches the current version."""
    version = _read_schema_version(path)
    return version is not None and version >= SCHEMA_VERSION


def init_db(db_path=None) -> Path:
    """Create delivery tables if missing. Idempotent."""
    if db_path is None:
        _migrate_legacy_storage()
    path = Path(db_path) if db_path else get_delivery_db_path()
    path_key = str(path.resolve())
    with _init_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path_key in _initialized_paths:
            return path
        if _schema_ready(path):
            _initialized_paths.add(path_key)
            return path

        with _cross_process_migration_lock(path):
            if _schema_ready(path):
                _initialized_paths.add(path_key)
                return path

            if _database_exists(path):
                _run_with_migration_retries(path, "upgrade")
            else:
                _run_with_migration_retries(path, "bootstrap")
        _initialized_paths.add(path_key)
    return path


@contextmanager
def connect(db_path=None) -> Iterator[sqlite3.Connection]:
    """Open a connection with schema initialized."""
    path = init_db(db_path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        _configure_connection(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def next_public_id(conn: sqlite3.Connection, prefix: str) -> str:
    """Generate sequential public IDs like WO-1, RD-2."""
    conn.execute(
        """
        INSERT INTO id_counters(prefix, value) VALUES (?, 1)
        ON CONFLICT(prefix) DO UPDATE SET value = value + 1
        """,
        (prefix,),
    )
    row = conn.execute(
        "SELECT value FROM id_counters WHERE prefix = ?",
        (prefix,),
    ).fetchone()
    return f"{prefix}-{row['value']}"


def ensure_delivery_root() -> Path:
    root = get_delivery_root()
    root.mkdir(parents=True, exist_ok=True)
    return root
