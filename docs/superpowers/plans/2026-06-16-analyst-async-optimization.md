# Analyst Async Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a faster, fail-soft, genuinely LLM-based daily Analyst scan using concurrency-limited Hermes analyst subagents, cache-aware automatic runs, and explicit per-ticket failure reporting.

**Architecture:** Add a `ReadinessAnalysisDispatcher` between Jira scope filtering and readiness persistence. The dispatcher computes stable input hashes, reuses cached records for automatic runs, and fans out LLM analysis through an `AnalystBackend` interface with concurrency `3`. The production backend uses Hermes async analyst subagents; an explicitly labeled conversation backend remains as a compatibility path, never as a heuristic fallback.

**Tech Stack:** Python 3, SQLite, FastAPI/Pydantic, asyncio, Hermes `AIAgent` / subagent runtime, Vite/React/TypeScript, pytest, Vitest.

---

## File Structure

Create focused Python units under `delivery_runtime/readiness/`:

- `delivery_runtime/readiness/analysis_dispatcher.py` owns `AnalysisOutcome`, `AnalysisDispatchSummary`, input hashing, concurrency limiting, cache decisions, and fail-soft aggregation.
- `delivery_runtime/readiness/analyst_backend.py` defines the `AnalystBackend` protocol and a deterministic `SynchronousAnalystBackend` adapter for existing callables.
- `lc_server/agent_bridge/hermes_analyst_subagent.py` owns the Hermes subagent-backed implementation and subagent API isolation.

Modify existing runtime files:

- `delivery_runtime/readiness/scanner.py` to call the dispatcher instead of serial `_analysis_runner`.
- `delivery_runtime/pm_inbox/daily_pipeline.py` and `delivery_runtime/pm_inbox/service.py` to pass `run_id` and `force`.
- `delivery_runtime/api/routes.py`, `delivery_runtime/api/schemas.py`, and `ui/src/lib/delivery.ts` to expose `force` and dispatch metrics.
- `delivery_runtime/persistence/db.py` and tests for schema version `12`.
- `delivery_runtime/readiness/analyst_prompt.py`, `lc_server/agent_bridge/hermes_analyst.py`, and `lc_server/agent_bridge/hermes_runtime.py` to align prompt quality and remove silent heuristic fallback from the daily scan path.

UI updates stay local to the dashboard analysis flow:

- `ui/src/app/delivery/use-daily-analysis.ts`
- `ui/src/app/delivery/kanban-routing.ts`
- `ui/src/app/delivery/kanban-board.tsx`
- related tests.

---

### Task 1: Persistence Fields And API Types

**Files:**
- Modify: `delivery_runtime/persistence/db.py`
- Modify: `delivery_runtime/api/schemas.py`
- Modify: `ui/src/lib/delivery.ts`
- Test: `tests/delivery_runtime/test_persistence.py`

- [ ] **Step 1: Write failing persistence test for analysis metadata columns**

Add this test to `tests/delivery_runtime/test_persistence.py`:

```python
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
```

- [ ] **Step 2: Run persistence test and verify failure**

Run:

```bash
python -m pytest tests/delivery_runtime/test_persistence.py::test_readiness_records_include_analysis_metadata_columns -q
```

Expected: FAIL because the new columns are missing.

- [ ] **Step 3: Add schema version 12 and fresh-schema columns**

In `delivery_runtime/persistence/db.py`, change:

```python
SCHEMA_VERSION = 11
```

to:

```python
SCHEMA_VERSION = 12
```

In the `CREATE TABLE IF NOT EXISTS readiness_records` block, after `estimated_days REAL,` add:

```sql
    analysis_input_hash TEXT,
    analysis_backend TEXT,
    last_analysis_error TEXT,
    last_analysis_failed_at TEXT,
```

- [ ] **Step 4: Add migration for existing databases**

In `delivery_runtime/persistence/db.py`, add:

```python
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
```

In `_apply_schema_migrations`, after the `estimated_days` migration block, add:

```python
    if "readiness_records" in tables:
        _migrate_analysis_metadata_columns(conn)
```

- [ ] **Step 5: Add API response types for dispatch metrics**

In `delivery_runtime/api/schemas.py`, before `PmInboxResponse`, add:

```python
class AnalysisDispatchItemResponse(BaseModel):
    jiraKey: str
    status: str
    backend: str | None = None
    durationMs: int | None = None
    error: str | None = None


class AnalysisDispatchResponse(BaseModel):
    backend: str = ""
    concurrency: int = 3
    success: int = 0
    cached: int = 0
    failed: int = 0
    skipped: int = 0
    forced: bool = False
    durationMs: int = 0
    items: list[AnalysisDispatchItemResponse] = Field(default_factory=list)
```

Then add this field to `PmInboxResponse`:

```python
    analysisDispatch: AnalysisDispatchResponse | None = None
```

- [ ] **Step 6: Add TypeScript payload types**

In `ui/src/lib/delivery.ts`, define:

```ts
export interface AnalysisDispatchItem {
  jiraKey: string
  status: 'success' | 'cached' | 'failed' | 'skipped' | string
  backend?: string | null
  durationMs?: number | null
  error?: string | null
}

export interface AnalysisDispatchPayload {
  backend: string
  concurrency: number
  success: number
  cached: number
  failed: number
  skipped: number
  forced: boolean
  durationMs: number
  items: AnalysisDispatchItem[]
}
```

Add this optional field to `PmInboxPayload`:

```ts
  analysisDispatch?: AnalysisDispatchPayload | null
```

- [ ] **Step 7: Run persistence tests**

Run:

```bash
python -m pytest tests/delivery_runtime/test_persistence.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 1**

```bash
git add delivery_runtime/persistence/db.py delivery_runtime/api/schemas.py ui/src/lib/delivery.ts tests/delivery_runtime/test_persistence.py
git commit -m "feat: add readiness analysis metadata fields"
```

---

### Task 2: Dispatcher Models, Hashing, Cache, And Concurrency

**Files:**
- Create: `delivery_runtime/readiness/analyst_backend.py`
- Create: `delivery_runtime/readiness/analysis_dispatcher.py`
- Test: `tests/delivery_runtime/test_analysis_dispatcher.py`

- [ ] **Step 1: Write dispatcher tests**

Create `tests/delivery_runtime/test_analysis_dispatcher.py`:

```python
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from delivery_runtime.readiness.analysis_dispatcher import (
    AnalysisCacheEntry,
    ReadinessAnalysisDispatcher,
    build_analysis_input_hash,
)


def _snapshot(key: str, description: str = "Acceptance criteria: render the page.") -> dict[str, Any]:
    return {
        "key": key,
        "projectKey": "TVP",
        "summary": f"Ticket {key}",
        "description": description,
        "issueType": "Task",
        "status": "To Do",
        "statusCategory": "To Do",
        "labels": ["front"],
        "comments": [],
    }


def _analysis(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "readinessScore": 82,
        "readinessStatus": "ready",
        "analysisSummary": f"{snapshot['key']} is ready.",
        "blockers": [],
        "recommendedRepos": ["tv5monde/tv5mondeplus-front"],
        "confidence": 0.82,
        "estimatedDays": 1.0,
        "jiraSnapshot": snapshot,
    }


class RecordingBackend:
    name = "recording"

    def __init__(self) -> None:
        self.running = 0
        self.max_running = 0
        self.calls: list[str] = []

    async def analyze_ticket(self, snapshot: dict[str, Any], *, project_key: str, run_id: str) -> dict[str, Any]:
        self.calls.append(snapshot["key"])
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        await asyncio.sleep(0.01)
        self.running -= 1
        return _analysis(snapshot)


class FailingBackend:
    name = "failing"

    async def analyze_ticket(self, snapshot: dict[str, Any], *, project_key: str, run_id: str) -> dict[str, Any]:
        if snapshot["key"] == "TVP-2":
            raise RuntimeError("LLM unavailable")
        return _analysis(snapshot)


@pytest.mark.asyncio
async def test_dispatcher_limits_concurrency_to_three():
    backend = RecordingBackend()
    dispatcher = ReadinessAnalysisDispatcher(backend=backend, concurrency=3)
    snapshots = [_snapshot(f"TVP-{index}") for index in range(1, 9)]

    result = await dispatcher.analyze_many(snapshots, project_key="TVP", run_id="DA-1", force=True)

    assert result.summary.success == 8
    assert result.summary.failed == 0
    assert backend.max_running == 3
    assert len(backend.calls) == 8


@pytest.mark.asyncio
async def test_dispatcher_uses_cache_when_not_forced():
    backend = RecordingBackend()
    snapshot = _snapshot("TVP-1")
    input_hash = build_analysis_input_hash(snapshot, project_key="TVP")
    dispatcher = ReadinessAnalysisDispatcher(
        backend=backend,
        concurrency=3,
        cache_lookup=lambda jira_key: AnalysisCacheEntry(
            jira_key=jira_key,
            analysis_input_hash=input_hash,
            analysis=_analysis(snapshot),
        ),
    )

    result = await dispatcher.analyze_many([snapshot], project_key="TVP", run_id="DA-1", force=False)

    assert result.summary.cached == 1
    assert result.summary.success == 0
    assert backend.calls == []
    assert result.outcomes[0].status == "cached"


@pytest.mark.asyncio
async def test_dispatcher_force_ignores_cache():
    backend = RecordingBackend()
    snapshot = _snapshot("TVP-1")
    input_hash = build_analysis_input_hash(snapshot, project_key="TVP")
    dispatcher = ReadinessAnalysisDispatcher(
        backend=backend,
        concurrency=3,
        cache_lookup=lambda jira_key: AnalysisCacheEntry(
            jira_key=jira_key,
            analysis_input_hash=input_hash,
            analysis=_analysis(snapshot),
        ),
    )

    result = await dispatcher.analyze_many([snapshot], project_key="TVP", run_id="DA-1", force=True)

    assert result.summary.cached == 0
    assert result.summary.success == 1
    assert backend.calls == ["TVP-1"]


@pytest.mark.asyncio
async def test_dispatcher_is_fail_soft():
    dispatcher = ReadinessAnalysisDispatcher(backend=FailingBackend(), concurrency=3)
    snapshots = [_snapshot("TVP-1"), _snapshot("TVP-2"), _snapshot("TVP-3")]

    result = await dispatcher.analyze_many(snapshots, project_key="TVP", run_id="DA-1", force=True)

    assert result.summary.success == 2
    assert result.summary.failed == 1
    failed = next(item for item in result.outcomes if item.jira_key == "TVP-2")
    assert failed.status == "failed"
    assert "LLM unavailable" in (failed.error or "")
```

- [ ] **Step 2: Run dispatcher tests and verify failure**

Run:

```bash
python -m pytest tests/delivery_runtime/test_analysis_dispatcher.py -q
```

Expected: FAIL because dispatcher modules do not exist.

- [ ] **Step 3: Create analyst backend protocol**

Create `delivery_runtime/readiness/analyst_backend.py`:

```python
"""Analyst LLM backend interfaces."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol


class AnalystBackend(Protocol):
    name: str

    async def analyze_ticket(
        self,
        snapshot: dict[str, Any],
        *,
        project_key: str,
        run_id: str,
    ) -> dict[str, Any]:
        ...


class SynchronousAnalystBackend:
    """Adapter for legacy synchronous analyst callables."""

    name = "hermes_conversation"

    def __init__(self, runner: Callable[[dict[str, Any], str], dict[str, Any]]) -> None:
        self._runner = runner

    async def analyze_ticket(
        self,
        snapshot: dict[str, Any],
        *,
        project_key: str,
        run_id: str,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._runner, snapshot, project_key)
```

- [ ] **Step 4: Create dispatcher implementation**

Create `delivery_runtime/readiness/analysis_dispatcher.py`:

```python
"""Concurrency-limited readiness analysis dispatch."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from delivery_runtime.readiness.analyst_backend import AnalystBackend

ANALYSIS_PROMPT_SCHEMA_VERSION = "analyst-v2"
AnalysisStatus = Literal["success", "cached", "failed", "skipped"]


@dataclass(frozen=True)
class AnalysisCacheEntry:
    jira_key: str
    analysis_input_hash: str | None
    analysis: dict[str, Any] | None


@dataclass(frozen=True)
class AnalysisOutcome:
    jira_key: str
    status: AnalysisStatus
    analysis: dict[str, Any] | None
    analysis_input_hash: str
    backend: str
    duration_ms: int
    error: str | None = None


@dataclass(frozen=True)
class AnalysisDispatchSummary:
    backend: str
    concurrency: int
    success: int
    cached: int
    failed: int
    skipped: int
    forced: bool
    duration_ms: int
    items: list[AnalysisOutcome] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "concurrency": self.concurrency,
            "success": self.success,
            "cached": self.cached,
            "failed": self.failed,
            "skipped": self.skipped,
            "forced": self.forced,
            "durationMs": self.duration_ms,
            "items": [
                {
                    "jiraKey": item.jira_key,
                    "status": item.status,
                    "backend": item.backend,
                    "durationMs": item.duration_ms,
                    "error": item.error,
                }
                for item in self.items
            ],
        }


@dataclass(frozen=True)
class AnalysisDispatchResult:
    outcomes: list[AnalysisOutcome]
    summary: AnalysisDispatchSummary


def build_analysis_input_hash(snapshot: dict[str, Any], *, project_key: str) -> str:
    payload = {
        "schemaVersion": ANALYSIS_PROMPT_SCHEMA_VERSION,
        "projectKey": project_key.strip().upper(),
        "key": snapshot.get("key"),
        "summary": snapshot.get("summary") or snapshot.get("title"),
        "description": snapshot.get("description"),
        "issueType": snapshot.get("issueType") or snapshot.get("issue_type"),
        "status": snapshot.get("status"),
        "statusCategory": snapshot.get("statusCategory"),
        "labels": snapshot.get("labels") or [],
        "assignee": snapshot.get("assignee") or snapshot.get("assigneeDisplayName"),
        "assigneeEmail": snapshot.get("assigneeEmail"),
        "comments": snapshot.get("comments") or [],
        "attachments": snapshot.get("attachments") or [],
        "attachmentExtracts": snapshot.get("attachmentExtracts") or [],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ReadinessAnalysisDispatcher:
    def __init__(
        self,
        *,
        backend: AnalystBackend,
        concurrency: int = 3,
        cache_lookup: Callable[[str], AnalysisCacheEntry | None] | None = None,
        per_ticket_timeout_sec: float = 180.0,
    ) -> None:
        self.backend = backend
        self.concurrency = max(1, min(int(concurrency), 3))
        self.cache_lookup = cache_lookup
        self.per_ticket_timeout_sec = per_ticket_timeout_sec

    async def analyze_many(
        self,
        snapshots: list[dict[str, Any]],
        *,
        project_key: str,
        run_id: str,
        force: bool,
    ) -> AnalysisDispatchResult:
        started = time.monotonic()
        semaphore = asyncio.Semaphore(self.concurrency)

        async def run_one(snapshot: dict[str, Any]) -> AnalysisOutcome:
            async with semaphore:
                return await self._analyze_one(
                    snapshot,
                    project_key=project_key,
                    run_id=run_id,
                    force=force,
                )

        outcomes = await asyncio.gather(*(run_one(snapshot) for snapshot in snapshots))
        duration_ms = int((time.monotonic() - started) * 1000)
        summary = AnalysisDispatchSummary(
            backend=getattr(self.backend, "name", "unknown"),
            concurrency=self.concurrency,
            success=sum(1 for item in outcomes if item.status == "success"),
            cached=sum(1 for item in outcomes if item.status == "cached"),
            failed=sum(1 for item in outcomes if item.status == "failed"),
            skipped=sum(1 for item in outcomes if item.status == "skipped"),
            forced=force,
            duration_ms=duration_ms,
            items=list(outcomes),
        )
        return AnalysisDispatchResult(outcomes=list(outcomes), summary=summary)

    async def _analyze_one(
        self,
        snapshot: dict[str, Any],
        *,
        project_key: str,
        run_id: str,
        force: bool,
    ) -> AnalysisOutcome:
        started = time.monotonic()
        jira_key = str(snapshot.get("key") or "").strip()
        analysis_input_hash = build_analysis_input_hash(snapshot, project_key=project_key)
        backend_name = getattr(self.backend, "name", "unknown")

        if not jira_key:
            return AnalysisOutcome(
                jira_key="",
                status="skipped",
                analysis=None,
                analysis_input_hash=analysis_input_hash,
                backend=backend_name,
                duration_ms=0,
                error="Missing Jira key",
            )

        if not force and self.cache_lookup is not None:
            cached = self.cache_lookup(jira_key)
            if cached and cached.analysis_input_hash == analysis_input_hash and cached.analysis:
                return AnalysisOutcome(
                    jira_key=jira_key,
                    status="cached",
                    analysis=cached.analysis,
                    analysis_input_hash=analysis_input_hash,
                    backend=backend_name,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )

        try:
            analysis = await asyncio.wait_for(
                self.backend.analyze_ticket(snapshot, project_key=project_key, run_id=run_id),
                timeout=self.per_ticket_timeout_sec,
            )
            analysis.setdefault("jiraSnapshot", snapshot)
            return AnalysisOutcome(
                jira_key=jira_key,
                status="success",
                analysis=analysis,
                analysis_input_hash=analysis_input_hash,
                backend=backend_name,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:
            return AnalysisOutcome(
                jira_key=jira_key,
                status="failed",
                analysis=None,
                analysis_input_hash=analysis_input_hash,
                backend=backend_name,
                duration_ms=int((time.monotonic() - started) * 1000),
                error=str(exc),
            )
```

- [ ] **Step 5: Run dispatcher tests**

Run:

```bash
python -m pytest tests/delivery_runtime/test_analysis_dispatcher.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add delivery_runtime/readiness/analyst_backend.py delivery_runtime/readiness/analysis_dispatcher.py tests/delivery_runtime/test_analysis_dispatcher.py
git commit -m "feat: add async readiness analysis dispatcher"
```

---

### Task 3: Wire Dispatcher Into Scanner And Daily Run Force Mode

**Files:**
- Modify: `delivery_runtime/readiness/scanner.py`
- Modify: `delivery_runtime/pm_inbox/daily_pipeline.py`
- Modify: `delivery_runtime/pm_inbox/service.py`
- Modify: `delivery_runtime/api/schemas.py`
- Modify: `delivery_runtime/api/routes.py`
- Modify: `ui/src/lib/delivery.ts`
- Test: `tests/delivery_runtime/test_daily_bn_analysis.py`

- [ ] **Step 1: Write daily pipeline test for forced manual run**

In `tests/delivery_runtime/test_daily_bn_analysis.py`, add:

```python
def test_manual_daily_analysis_forces_dispatcher_even_when_cached(_isolate_hermes_home):
    install_phase25_project_mapping()
    init_db()

    from delivery_runtime.readiness.analysis_dispatcher import AnalysisCacheEntry
    from delivery_runtime.readiness.analyst_backend import SynchronousAnalystBackend
    from delivery_runtime.readiness.scanner import ReadinessScanner

    calls: list[str] = []
    snapshots = [_ready_snapshot("AAC-701")]

    def runner(snapshot: dict, project_key: str) -> dict:
        calls.append(snapshot["key"])
        return {
            "readinessScore": 90,
            "readinessStatus": "ready",
            "analysisSummary": "Fresh LLM result",
            "blockers": [],
            "recommendedRepos": ["group/bn-frontend"],
            "confidence": 0.9,
            "estimatedDays": 1.0,
            "jiraSnapshot": snapshot,
        }

    scanner = ReadinessScanner(
        issue_fetcher=lambda _project: snapshots,
        analysis_backend=SynchronousAnalystBackend(runner),
        cache_lookup=lambda _jira_key: AnalysisCacheEntry(
            jira_key="AAC-701",
            analysis_input_hash="stale",
            analysis=runner(snapshots[0]),
        ),
    )
    calls.clear()
    pipeline = DailyAnalysisPipeline(scanner=scanner)

    result = pipeline.run("AAC", force=True)

    assert calls == ["AAC-701"]
    assert result["analysisDispatch"]["forced"] is True
    assert result["analysisDispatch"]["success"] == 1
```

- [ ] **Step 2: Write automatic cache reuse test**

Add:

```python
def test_automatic_daily_analysis_reuses_cached_result(_isolate_hermes_home):
    install_phase25_project_mapping()
    init_db()

    from delivery_runtime.readiness.analysis_dispatcher import (
        AnalysisCacheEntry,
        build_analysis_input_hash,
    )
    from delivery_runtime.readiness.analyst_backend import SynchronousAnalystBackend
    from delivery_runtime.readiness.scanner import ReadinessScanner

    calls: list[str] = []
    snapshot = _ready_snapshot("AAC-702")
    cached_analysis = {
        "readinessScore": 88,
        "readinessStatus": "ready",
        "analysisSummary": "Cached LLM result",
        "blockers": [],
        "recommendedRepos": ["group/bn-frontend"],
        "confidence": 0.88,
        "estimatedDays": 1.0,
        "jiraSnapshot": snapshot,
    }
    input_hash = build_analysis_input_hash(snapshot, project_key="AAC")

    def runner(snapshot: dict, project_key: str) -> dict:
        calls.append(snapshot["key"])
        return cached_analysis

    scanner = ReadinessScanner(
        issue_fetcher=lambda _project: [snapshot],
        analysis_backend=SynchronousAnalystBackend(runner),
        cache_lookup=lambda _jira_key: AnalysisCacheEntry(
            jira_key="AAC-702",
            analysis_input_hash=input_hash,
            analysis=cached_analysis,
        ),
    )
    pipeline = DailyAnalysisPipeline(scanner=scanner)

    result = pipeline.run("AAC", force=False)

    assert calls == []
    assert result["analysisDispatch"]["cached"] == 1
    assert result["analysisDispatch"]["success"] == 0
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
python -m pytest tests/delivery_runtime/test_daily_bn_analysis.py::test_manual_daily_analysis_forces_dispatcher_even_when_cached tests/delivery_runtime/test_daily_bn_analysis.py::test_automatic_daily_analysis_reuses_cached_result -q
```

Expected: FAIL because scanner does not accept `analysis_backend`, `cache_lookup`, or `force`.

- [ ] **Step 4: Update scanner constructor and result**

In `delivery_runtime/readiness/scanner.py`, import:

```python
import asyncio

from delivery_runtime.readiness.analysis_dispatcher import (
    AnalysisCacheEntry,
    AnalysisDispatchSummary,
    ReadinessAnalysisDispatcher,
)
from delivery_runtime.readiness.analyst_backend import AnalystBackend, SynchronousAnalystBackend
```

Add to `ReadinessScanResult`:

```python
    analysis_dispatch: dict[str, Any] | None = None
```

Update `ReadinessScanner.__init__` signature:

```python
        analysis_runner: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
        analysis_backend: AnalystBackend | None = None,
        cache_lookup: Callable[[str], AnalysisCacheEntry | None] | None = None,
        analysis_concurrency: int = 3,
```

Inside `__init__`, set:

```python
        if analysis_backend is not None:
            self._analysis_backend = analysis_backend
        else:
            runner = analysis_runner or (lambda snapshot, project_key: analyze_ticket_snapshot(snapshot))
            self._analysis_backend = SynchronousAnalystBackend(runner)
        self._cache_lookup = cache_lookup
        self._analysis_concurrency = analysis_concurrency
```

Remove direct reliance on `self._analysis_runner` for new code.

- [ ] **Step 5: Update `scan_project` to dispatch analysis**

Change signature:

```python
    def scan_project(
        self,
        project_key: str,
        *,
        run_id: str = "",
        force: bool = False,
    ) -> ReadinessScanResult:
```

Replace the loop body that calls `_analysis_runner` with collection of `pending_snapshots`, then call:

```python
        dispatcher = ReadinessAnalysisDispatcher(
            backend=self._analysis_backend,
            concurrency=self._analysis_concurrency,
            cache_lookup=self._cache_lookup,
        )
        dispatch_result = asyncio.run(
            dispatcher.analyze_many(
                pending_snapshots,
                project_key=project_key,
                run_id=run_id or "manual",
                force=force,
            )
        )
        pending_upserts = [
            (outcome.analysis["jiraSnapshot"], outcome)
            for outcome in dispatch_result.outcomes
            if outcome.status in {"success", "cached"} and outcome.analysis is not None
        ]
```

When upserting, pass `outcome` instead of raw analysis:

```python
                analysis = outcome.analysis or {}
                record_id, was_created = self._upsert_record(
                    conn,
                    jira_key=jira_key,
                    project_key=project_key,
                    analysis=analysis,
                    analysis_input_hash=outcome.analysis_input_hash,
                    analysis_backend=outcome.backend,
                )
```

Return:

```python
            analysis_dispatch=dispatch_result.summary.to_dict(),
```

- [ ] **Step 6: Update `_upsert_record` for metadata**

Change `_upsert_record` signature:

```python
        analysis_input_hash: str | None = None,
        analysis_backend: str | None = None,
```

In update SQL, add:

```sql
                    analysis_input_hash = ?,
                    analysis_backend = ?,
                    last_analysis_error = NULL,
                    last_analysis_failed_at = NULL,
```

with params:

```python
                    analysis_input_hash,
                    analysis_backend,
```

In insert SQL, add the columns and values:

```sql
                analysis_input_hash, analysis_backend, last_analysis_error, last_analysis_failed_at,
```

and:

```python
                analysis_input_hash,
                analysis_backend,
                None,
                None,
```

- [ ] **Step 7: Pass force through pipeline and service**

In `delivery_runtime/pm_inbox/daily_pipeline.py`, change:

```python
    def run(self, project_key: str | None = None, *, run_id: str | None = None) -> dict[str, Any]:
```

to:

```python
    def run(
        self,
        project_key: str | None = None,
        *,
        run_id: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
```

Change scanner call:

```python
            scan_result = self.scanner.scan_project(project_key, run_id=run_id, force=force)
```

Add to `pipeline_payload`:

```python
                "analysisDispatch": scan_result.analysis_dispatch or {},
```

In `delivery_runtime/pm_inbox/service.py`, add `force: bool = False` to `run_daily_analysis` and pass it to `self.pipeline.run(key, run_id=run_id, force=force)`.

- [ ] **Step 8: Add API force field and route propagation**

In `delivery_runtime/api/schemas.py`, change:

```python
class DailyAnalysisRunRequest(BaseModel):
    projectKey: str | None = None
```

to:

```python
class DailyAnalysisRunRequest(BaseModel):
    projectKey: str | None = None
    force: bool = False
```

In `delivery_runtime/api/routes.py`, change `_run_daily_analysis_background`:

```python
def _run_daily_analysis_background(services, project_key: str, run_id: str, force: bool) -> None:
    try:
        services.pm_inbox.run_daily_analysis(project_key, run_id=run_id, force=force)
```

and enqueue:

```python
    force = bool(body.force) if body else False
    background_tasks.add_task(_run_daily_analysis_background, services, resolved_key, run_id, force)
    return {"status": "started", "projectKey": resolved_key, "runId": run_id, "force": force}
```

- [ ] **Step 9: Update frontend API call**

In `ui/src/lib/delivery.ts`, change `runDailyAnalysis` to accept `force`:

```ts
export async function runDailyAnalysis(projectKey?: string, options: { force?: boolean } = {}) {
  return request<DailyAnalysisResult>('/delivery/pm-inbox/daily-analysis/run', {
    method: 'POST',
    body: JSON.stringify({ projectKey, force: options.force ?? true }),
    timeoutMs: 30_000
  })
}
```

The dashboard manual path uses the default `force: true`.

- [ ] **Step 10: Run backend daily tests**

Run:

```bash
python -m pytest tests/delivery_runtime/test_daily_bn_analysis.py tests/delivery_runtime/test_analysis_dispatcher.py -q
```

Expected: PASS.

- [ ] **Step 11: Commit Task 3**

```bash
git add delivery_runtime/readiness/scanner.py delivery_runtime/pm_inbox/daily_pipeline.py delivery_runtime/pm_inbox/service.py delivery_runtime/api/schemas.py delivery_runtime/api/routes.py ui/src/lib/delivery.ts tests/delivery_runtime/test_daily_bn_analysis.py
git commit -m "feat: wire async analyst dispatch into daily scans"
```

---

### Task 4: Fail-Soft Persistence For Ticket Analysis Failures

**Files:**
- Modify: `delivery_runtime/readiness/scanner.py`
- Modify: `delivery_runtime/pm_inbox/inbox.py`
- Modify: `delivery_runtime/pm_inbox/execution_queue.py`
- Modify: `delivery_runtime/pm_inbox/sprint_selection.py`
- Test: `tests/delivery_runtime/test_analysis_dispatcher.py`
- Test: `tests/delivery_runtime/test_daily_bn_analysis.py`

- [ ] **Step 1: Write test for failed ticket with previous analysis**

Add to `tests/delivery_runtime/test_daily_bn_analysis.py`:

```python
def test_failed_analysis_preserves_previous_readiness_record(_isolate_hermes_home):
    install_phase25_project_mapping()
    init_db()

    from delivery_runtime.readiness.analyst_backend import SynchronousAnalystBackend
    from delivery_runtime.readiness.scanner import ReadinessScanner

    snapshot = _ready_snapshot("AAC-801")
    with connect() as conn:
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO readiness_records (
                id, jira_key, project_key, title, readiness_score, readiness_status,
                analysis_summary, blockers_json, recommended_repos_json, confidence,
                estimated_days, jira_snapshot_json, analyzed_at, created_at, updated_at
            ) VALUES ('RD-801', 'AAC-801', 'AAC', 'Previous ready', 88, 'ready',
                      'Previous LLM result', '[]', '["group/bn-frontend"]', 0.88,
                      1.0, ?, ?, ?, ?)
            """,
            (json_dumps(snapshot), now, now, now),
        )

    def failing_runner(snapshot: dict, project_key: str) -> dict:
        raise RuntimeError("subagent timeout")

    scanner = ReadinessScanner(
        issue_fetcher=lambda _project: [snapshot],
        analysis_backend=SynchronousAnalystBackend(failing_runner),
    )
    pipeline = DailyAnalysisPipeline(scanner=scanner)
    result = pipeline.run("AAC", force=True)

    assert result["analysisDispatch"]["failed"] == 1
    with connect() as conn:
        row = conn.execute(
            "SELECT readiness_status, last_analysis_error FROM readiness_records WHERE jira_key = 'AAC-801'"
        ).fetchone()
    assert row["readiness_status"] == "ready"
    assert "subagent timeout" in row["last_analysis_error"]
```

- [ ] **Step 2: Write test for failed ticket with no previous analysis**

Add:

```python
def test_failed_analysis_without_previous_record_creates_analysis_failed(_isolate_hermes_home):
    install_phase25_project_mapping()
    init_db()

    from delivery_runtime.readiness.analyst_backend import SynchronousAnalystBackend
    from delivery_runtime.readiness.scanner import ReadinessScanner

    snapshot = _ready_snapshot("AAC-802")

    def failing_runner(snapshot: dict, project_key: str) -> dict:
        raise RuntimeError("subagent timeout")

    scanner = ReadinessScanner(
        issue_fetcher=lambda _project: [snapshot],
        analysis_backend=SynchronousAnalystBackend(failing_runner),
    )
    pipeline = DailyAnalysisPipeline(scanner=scanner)
    result = pipeline.run("AAC", force=True)

    assert result["analysisDispatch"]["failed"] == 1
    with connect() as conn:
        row = conn.execute(
            "SELECT readiness_status, last_analysis_error FROM readiness_records WHERE jira_key = 'AAC-802'"
        ).fetchone()
    assert row["readiness_status"] == "analysis_failed"
    assert "subagent timeout" in row["last_analysis_error"]
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
python -m pytest tests/delivery_runtime/test_daily_bn_analysis.py::test_failed_analysis_preserves_previous_readiness_record tests/delivery_runtime/test_daily_bn_analysis.py::test_failed_analysis_without_previous_record_creates_analysis_failed -q
```

Expected: FAIL because failed outcomes are not persisted.

- [ ] **Step 4: Add scanner failure persistence**

In `delivery_runtime/readiness/scanner.py`, add helper:

```python
    @staticmethod
    def _record_analysis_failure(
        conn,
        *,
        jira_key: str,
        project_key: str,
        snapshot: dict[str, Any],
        error: str,
        analysis_input_hash: str,
        analysis_backend: str,
    ) -> str:
        now = utc_now_iso()
        existing = conn.execute(
            """
            SELECT id FROM readiness_records
            WHERE jira_key = ? AND readiness_status NOT IN ('promoted', 'dismissed')
            """,
            (jira_key,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE readiness_records SET
                    last_analysis_error = ?,
                    last_analysis_failed_at = ?,
                    analysis_input_hash = ?,
                    analysis_backend = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (error, now, analysis_input_hash, analysis_backend, now, existing["id"]),
            )
            return str(existing["id"])

        record_id = next_public_id(conn, "RD")
        title = str(snapshot.get("summary") or snapshot.get("title") or jira_key)
        conn.execute(
            """
            INSERT INTO readiness_records (
                id, jira_key, project_key, title, readiness_score, readiness_status,
                analysis_summary, blockers_json, recommended_repos_json, confidence,
                estimated_days, jira_snapshot_json, analyzed_at,
                analysis_input_hash, analysis_backend, last_analysis_error, last_analysis_failed_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, 0, 'analysis_failed',
                      'LLM analysis failed before producing a valid readiness result.',
                      '[]', '[]', 0, NULL, ?, NULL, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                jira_key,
                project_key,
                title,
                json_dumps(snapshot),
                analysis_input_hash,
                analysis_backend,
                error,
                now,
                now,
                now,
            ),
        )
        return record_id
```

After successful upserts in `scan_project`, loop over failed outcomes and call `_record_analysis_failure`.

- [ ] **Step 5: Include `analysis_failed` in inbox visibility but not execution**

In `delivery_runtime/pm_inbox/execution_queue.py`, update `_queue_status`:

```python
    if readiness_status == "analysis_failed":
        return "blocked"
```

In `delivery_runtime/pm_inbox/sprint_selection.py`, include `analysis_failed` in `_SPRINT_BACKLOG_STATUSES` only if the dashboard should show failed tickets in sprint backlog:

```python
_SPRINT_BACKLOG_STATUSES = ("ready", "needs_clarification", "not_ready", "analysis_failed")
```

When building warnings:

```python
        elif status == "analysis_failed":
            warnings.append("Latest LLM analysis failed; review the error before promotion")
```

- [ ] **Step 6: Run daily tests**

Run:

```bash
python -m pytest tests/delivery_runtime/test_daily_bn_analysis.py tests/delivery_runtime/test_analysis_dispatcher.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add delivery_runtime/readiness/scanner.py delivery_runtime/pm_inbox/execution_queue.py delivery_runtime/pm_inbox/sprint_selection.py tests/delivery_runtime/test_daily_bn_analysis.py
git commit -m "feat: record fail-soft analyst outcomes"
```

---

### Task 5: Compact Analyst Prompt And Parser Alignment

**Files:**
- Modify: `delivery_runtime/readiness/analyst_prompt.py`
- Modify: `lc_server/agent_bridge/hermes_analyst.py`
- Modify: `lc_server/agent_bridge/hermes_runtime.py`
- Test: `tests/lc_server/test_hermes_analyst.py`
- Test: `tests/delivery_runtime/test_ticket_quality.py`

- [ ] **Step 1: Write prompt regression test for technical tickets**

Add to `tests/lc_server/test_hermes_analyst.py`:

```python
def test_analyst_prompt_says_technical_tickets_do_not_need_gherkin():
    prompt = build_analyst_user_prompt(
        {
            "key": "TVP-2391",
            "projectKey": "TVP",
            "summary": "Add schema.org FAQPage JSON-LD on film category pages",
            "description": "Add JSON-LD blocks for FAQPage on /films pages with the exact properties listed.",
            "issueType": "Task",
            "status": "À FAIRE",
        }
    )

    lowered = prompt.lower()
    assert "do not require formal gherkin" in lowered
    assert "schema.org" in lowered
    assert "development work" in lowered
```

- [ ] **Step 2: Write no silent heuristic fallback test**

In `tests/lc_server/test_hermes_analyst.py`, add a test around `HermesRuntimeBridge.run_readiness_analysis` where the analyst raises `AnalystParseError` and assert the result has `readinessStatus == "analysis_failed"` instead of a heuristic status:

```python
@pytest.mark.asyncio
async def test_run_readiness_analysis_returns_analysis_failed_on_parse_error():
    from delivery_runtime.readiness.analyst_prompt import AnalystParseError
    from lc_server.agent_bridge.hermes_runtime import HermesRuntimeBridge

    class ReadyRegistry:
        def is_automation_ready(self, project_key: str) -> bool:
            return True

    class FailingAnalyst:
        def analyze(self, snapshot: dict, project_key: str) -> dict:
            raise AnalystParseError("bad JSON")

    bridge = HermesRuntimeBridge(registry=ReadyRegistry(), analyst=FailingAnalyst())

    result = await bridge.run_readiness_analysis("TVP-1", {"projectKey": "TVP", "snapshot": {"key": "TVP-1"}})

    assert result["readinessStatus"] == "analysis_failed"
    assert "bad JSON" in result["analysisSummary"]
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
python -m pytest tests/lc_server/test_hermes_analyst.py -q
```

Expected: FAIL until prompt and fallback behavior are updated.

- [ ] **Step 4: Update compact prompt content**

In `delivery_runtime/readiness/analyst_prompt.py`, add this section to `build_analyst_user_prompt` before the raw JSON block:

```python
        "## LivingColor readiness rules",
        "",
        "- ready: enough information to implement safely.",
        "- needs_clarification: missing product or QA information blocks implementation.",
        "- not_ready: blocked, contradictory, or technically impossible right now.",
        "- not_development: editorial, support, process-only, or outside development delivery.",
        "",
        "Do not require formal Gherkin acceptance criteria if the expected code change is clear.",
        "SEO JSON-LD, schema.org, dataLayer, Airship tracking, BFF behavior, frontend UI, and playback/access bugs are development work unless the ticket explicitly says otherwise.",
        "Prefer ready when the title, description, target behavior, and repository mapping are sufficient and no unresolved comment blocks exist.",
```

Keep the current JSON schema instructions after this block.

- [ ] **Step 5: Remove silent heuristic fallback from Hermes runtime**

In `lc_server/agent_bridge/hermes_runtime.py`, change the `except AnalystParseError` block to return an explicit analysis failure:

```python
            except AnalystParseError as exc:
                logger.warning("Analyst run failed for %s (%s)", jira_key, exc)
                return {
                    "readinessScore": 0,
                    "readinessStatus": "analysis_failed",
                    "analysisSummary": f"LLM analyst failed before producing valid readiness JSON: {exc}",
                    "blockers": [str(exc)],
                    "recommendedRepos": [],
                    "confidence": 0.0,
                    "estimatedDays": None,
                    "jiraSnapshot": snapshot,
                }
```

Keep the non-provisioned fallback to `analyze_ticket_snapshot(snapshot)` only for projects that are not automation-ready.

- [ ] **Step 6: Update parser to accept analysis_failed**

In `delivery_runtime/readiness/analyst_prompt.py`, update `_normalize_analyst_readiness_status`:

```python
    aliases = {
        "notready": "not_ready",
        "needsclarification": "needs_clarification",
        "notdevelopment": "not_development",
        "analysisfailed": "analysis_failed",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in {"ready", "not_ready", "needs_clarification", "not_development", "analysis_failed"}:
        return normalized
```

- [ ] **Step 7: Run analyst tests**

Run:

```bash
python -m pytest tests/lc_server/test_hermes_analyst.py tests/delivery_runtime/test_ticket_quality.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 5**

```bash
git add delivery_runtime/readiness/analyst_prompt.py lc_server/agent_bridge/hermes_runtime.py tests/lc_server/test_hermes_analyst.py tests/delivery_runtime/test_ticket_quality.py
git commit -m "fix: align analyst prompt and LLM failure handling"
```

---

### Task 6: Hermes Subagent Analyst Backend

**Files:**
- Create: `lc_server/agent_bridge/hermes_analyst_subagent.py`
- Modify: `lc_server/factory.py`
- Test: `tests/lc_server/test_hermes_analyst_subagent.py`

- [ ] **Step 1: Write backend contract tests with a fake launcher**

Create `tests/lc_server/test_hermes_analyst_subagent.py`:

```python
from __future__ import annotations

import pytest

from lc_server.agent_bridge.hermes_analyst_subagent import HermesSubagentAnalystBackend


def _completion() -> str:
    return """
```json
{
  "readinessScore": 86,
  "readinessStatus": "ready",
  "analysisSummary": "TVP-1 is ready for delivery.",
  "blockers": [],
  "recommendedRepos": ["tv5monde/tv5mondeplus-front"],
  "confidence": 0.86,
  "estimatedDays": 1
}
```
"""


@pytest.mark.asyncio
async def test_subagent_backend_parses_launcher_response():
    calls = []

    async def fake_launcher(*, task_id: str, prompt: str, project_key: str) -> str:
        calls.append({"task_id": task_id, "prompt": prompt, "project_key": project_key})
        return _completion()

    backend = HermesSubagentAnalystBackend(launcher=fake_launcher)
    snapshot = {
        "key": "TVP-1",
        "projectKey": "TVP",
        "summary": "Add JSON-LD",
        "description": "Add the exact schema.org JSON-LD block.",
        "issueType": "Task",
        "status": "To Do",
    }

    result = await backend.analyze_ticket(snapshot, project_key="TVP", run_id="DA-1")

    assert result["readinessStatus"] == "ready"
    assert result["estimatedDays"] == 1.0
    assert calls[0]["task_id"] == "delivery-analyst-TVP-1-DA-1"
    assert "schema.org" in calls[0]["prompt"]
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
python -m pytest tests/lc_server/test_hermes_analyst_subagent.py -q
```

Expected: FAIL because the backend file does not exist.

- [ ] **Step 3: Implement subagent backend wrapper**

Create `lc_server/agent_bridge/hermes_analyst_subagent.py`:

```python
"""Hermes async subagent backend for LivingColor Analyst runs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from delivery_runtime.readiness.analyst_prompt import (
    build_analyst_user_prompt,
    parse_analyst_completion,
)
from lc_server.integrations.skills import (
    EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER,
    external_guidance_for_skills,
)

SubagentLauncher = Callable[..., Awaitable[str]]


class HermesSubagentAnalystBackend:
    name = "hermes_subagent"

    def __init__(self, *, launcher: SubagentLauncher | None = None) -> None:
        self._launcher = launcher or _default_subagent_launcher

    async def analyze_ticket(
        self,
        snapshot: dict[str, Any],
        *,
        project_key: str,
        run_id: str,
    ) -> dict[str, Any]:
        jira_key = str(snapshot.get("key") or "").strip()
        task_id = f"delivery-analyst-{jira_key or project_key}-{run_id}"
        prompt = build_analyst_user_prompt(snapshot)
        guidance = external_guidance_for_skills(("ticket-analyst",))
        if guidance:
            prompt = f"{prompt}\n\n{guidance}\n\n{EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER}"

        final_response = await self._launcher(
            task_id=task_id,
            prompt=prompt,
            project_key=project_key.strip().upper(),
        )
        return parse_analyst_completion(str(final_response or ""), snapshot)


async def _default_subagent_launcher(*, task_id: str, prompt: str, project_key: str) -> str:
    """Launch a read-only Hermes analyst subagent and return its final response."""
    from hermes_cli.subagents import run_subagent

    result = await run_subagent(
        task_id=task_id,
        prompt=prompt,
        readonly=True,
        model=None,
        metadata={"projectKey": project_key, "role": "analyst"},
    )
    if isinstance(result, dict):
        return str(result.get("final_response") or result.get("finalResponse") or "")
    return str(result or "")
```

The implementation contract for this plan is `hermes_cli.subagents.run_subagent(...)`. Keep all Hermes-specific imports inside `_default_subagent_launcher` so tests can inject a fake launcher without importing Hermes.

- [ ] **Step 4: Wire production scanner to subagent backend**

In `lc_server/factory.py`, import:

```python
from lc_server.agent_bridge.hermes_analyst_subagent import HermesSubagentAnalystBackend
```

Build the scanner with:

```python
    scanner = ReadinessScanner(
        events,
        issue_fetcher=fetch_issues_for_readiness,
        analysis_backend=HermesSubagentAnalystBackend(),
    )
```

Keep `ReadinessService(... analysis_runner=_analysis_runner ...)` for individual re-analysis until that path is separately converted.

- [ ] **Step 5: Run backend tests**

Run:

```bash
python -m pytest tests/lc_server/test_hermes_analyst_subagent.py tests/delivery_runtime/test_analysis_dispatcher.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```bash
git add lc_server/agent_bridge/hermes_analyst_subagent.py lc_server/factory.py tests/lc_server/test_hermes_analyst_subagent.py
git commit -m "feat: add Hermes subagent analyst backend"
```

---

### Task 7: UI Run Summary And Failed Ticket Display

**Files:**
- Modify: `ui/src/app/delivery/use-daily-analysis.ts`
- Modify: `ui/src/app/delivery/kanban-routing.ts`
- Modify: `ui/src/app/delivery/kanban-board.tsx`
- Modify: `ui/src/app/delivery/types.ts`
- Test: `ui/src/app/delivery/kanban-routing.test.ts`
- Test: `ui/src/app/delivery/kanban-board.test.tsx`

- [ ] **Step 1: Add UI tests for failed cards and summary data**

In `ui/src/app/delivery/kanban-routing.test.ts`, add:

```ts
it('shows analysis_failed sprint tickets without an approve CTA', () => {
  const inbox = makeInbox()
  inbox.selectedSprint.tickets = [
    {
      readinessId: 'R-failed',
      jiraKey: 'TVP-999',
      title: 'Analysis failed',
      estimatedDays: 0,
      priorityRank: 2,
      urgencyScore: 0,
      warnings: ['Latest LLM analysis failed; review the error before promotion'],
      readinessStatus: 'analysis_failed'
    }
  ]

  const columns = buildKanbanColumns(inbox, [])
  const card = columns.find(column => column.id === 'sprint')!.cards[0]

  expect(card.jiraKey).toBe('TVP-999')
  expect(card.ctaLabel).toBeUndefined()
  expect(card.readinessStatus).toBe('analysis_failed')
})
```

- [ ] **Step 2: Run UI test and verify failure**

Run:

```bash
cd ui && npm run test -- --run src/app/delivery/kanban-routing.test.ts
```

Expected: FAIL if `analysis_failed` cards still get an approval CTA or status is not passed through.

- [ ] **Step 3: Update kanban routing**

In `ui/src/app/delivery/kanban-routing.ts`, ensure `sprintCtaForTicket` returns `undefined` for `analysis_failed`:

```ts
  if (status === 'analysis_failed') {
    return undefined
  }
```

Add `readinessStatus` to the sprint card object if missing:

```ts
      readinessStatus: ticket.readinessStatus,
```

- [ ] **Step 4: Show warning text on card**

Extend `KanbanCard` with:

```ts
  warnings?: string[]
```

Pass `warnings: ticket.warnings` from `kanban-routing.ts`.

In `kanban-board.tsx`, below metadata, render:

```tsx
        {card.warnings?.length ? (
          <div className="mt-2 rounded-md border border-amber-400/40 bg-amber-400/10 px-2 py-1 text-[10px] text-amber-100">
            {card.warnings[0]}
          </div>
        ) : null}
```

- [ ] **Step 5: Improve completion toast**

In `ui/src/app/delivery/use-daily-analysis.ts`, update `finishDailyAnalysis` to prefer `inbox.analysisDispatch`:

```ts
  const dispatch = inbox.analysisDispatch
  const summary =
    dispatch != null
      ? `LLM analysis complete: ${lastRun?.jiraSynced ?? 0} in scope, ${dispatch.success} analyzed, ${dispatch.cached} cached, ${dispatch.failed} failed.`
      : lastRun != null
        ? `Daily analysis complete: ${lastRun.jiraSynced ?? 0} in scope, ${lastRun.analyzed ?? 0} analyzed.`
        : 'Daily analysis complete.'
```

- [ ] **Step 6: Run UI tests**

Run:

```bash
cd ui && npm run test -- --run src/app/delivery/kanban-routing.test.ts src/app/delivery/kanban-board.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Build UI**

Run:

```bash
cd ui && npm run build
```

Expected: PASS and updated `dashboard/dist/index.js` / `dashboard/dist/style.css`.

- [ ] **Step 8: Commit Task 7**

```bash
git add ui/src/app/delivery/use-daily-analysis.ts ui/src/app/delivery/kanban-routing.ts ui/src/app/delivery/kanban-board.tsx ui/src/app/delivery/types.ts ui/src/app/delivery/kanban-routing.test.ts ui/src/app/delivery/kanban-board.test.tsx ui/src/lib/delivery.ts dashboard/dist/index.js dashboard/dist/style.css
git commit -m "feat: surface async analyst run outcomes"
```

---

### Task 8: End-To-End Verification And Deployment

**Files:**
- Modify only if earlier tasks reveal wiring issues.

- [ ] **Step 1: Run focused backend suite**

Run:

```bash
python -m pytest \
  tests/delivery_runtime/test_analysis_dispatcher.py \
  tests/delivery_runtime/test_daily_bn_analysis.py \
  tests/delivery_runtime/test_persistence.py \
  tests/lc_server/test_hermes_analyst.py \
  tests/lc_server/test_hermes_analyst_subagent.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run focused UI suite**

Run:

```bash
cd ui && npm run test -- --run \
  src/app/delivery/kanban-routing.test.ts \
  src/app/delivery/kanban-board.test.tsx \
  src/app/delivery/project-dashboard.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Build dashboard**

Run:

```bash
cd ui && npm run build
```

Expected: PASS.

- [ ] **Step 4: Sync plugin and restart Hermes**

Run:

```bash
./scripts/sync-hermes-plugin.sh && hermes gateway restart
```

Expected:

```text
Done. Restart Hermes to load backend + dashboard changes:
  hermes gateway restart
✓ Service restarted
```

- [ ] **Step 5: Verify manual TVP daily analysis behavior**

From the dashboard, click `Run analysis`.

Expected:

- The request body includes `force: true`.
- `daily_analysis_runs.pipeline_json` includes `analysisDispatch.forced = true`.
- `analysisDispatch.concurrency = 3`.
- No log says `falling back to heuristic analysis`.
- Failed tickets are visible per ticket instead of failing the whole run.

Use read-only DB check:

```bash
sqlite3 ~/.hermes/livingcolor/runtime.db "SELECT json_extract(pipeline_json, '$.analysisDispatch') FROM daily_analysis_runs ORDER BY started_at DESC LIMIT 1;"
```

- [ ] **Step 6: Verify automatic cache behavior with a direct service call in tests only**

Do not trigger production scheduler manually. Confirm with automated tests that `force=False` reuses cache.

Run:

```bash
python -m pytest tests/delivery_runtime/test_daily_bn_analysis.py::test_automatic_daily_analysis_reuses_cached_result -q
```

Expected: PASS.

- [ ] **Step 7: Final status check**

Run:

```bash
git status --short
```

Expected: only intentional build artifacts or no changes. If build artifacts changed in Step 3, include them in the final implementation commit.

- [ ] **Step 8: Commit final verification fixes if needed**

If Step 7 shows intentional build or verification changes, stage the exact files shown by `git status --short`. For example, when only dashboard build artifacts changed:

```bash
git add dashboard/dist/index.js dashboard/dist/style.css
git commit -m "fix: finalize async analyst optimization wiring"
```

If Step 7 is clean, do not create an empty commit.

---

## Self-Review Notes

Spec coverage:

- Async fan-out and concurrency `3`: Tasks 2, 3, 6.
- Manual force and automatic cache: Tasks 2, 3, 8.
- Fail-soft per-ticket errors: Task 4.
- Hermes subagent backend: Task 6.
- Prompt/schema alignment: Task 5.
- UI run summary and failed-ticket visibility: Task 7.
- Persistence and migration: Task 1.
- Verification and deployment: Task 8.

No placeholders remain in executable task steps. The Hermes subagent integration is isolated in `_default_subagent_launcher` and uses the concrete `hermes_cli.subagents.run_subagent` contract while keeping tests injectable through the public backend constructor.
