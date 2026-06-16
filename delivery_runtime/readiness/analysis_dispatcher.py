"""Async readiness analysis dispatcher."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from delivery_runtime.readiness.analyst_backend import AnalystBackend

ANALYSIS_PROMPT_SCHEMA_VERSION = "analyst-v2"

AnalysisOutcomeStatus = Literal["success", "cached", "failed", "skipped"]
CacheLookup = Callable[[str], "AnalysisCacheEntry | None"]


@dataclass(frozen=True)
class AnalysisCacheEntry:
    jira_key: str
    analysis_input_hash: str | None
    analysis: dict[str, Any] | None


@dataclass(frozen=True)
class AnalysisOutcome:
    jira_key: str
    status: AnalysisOutcomeStatus
    analysis_input_hash: str
    duration_ms: int
    analysis: dict[str, Any] | None = None
    error: str | None = None
    backend: str | None = None


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
    items: list[AnalysisOutcome]

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
    """Build a stable hash for the Jira fields that affect analyst output."""

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
        cache_lookup: CacheLookup | None = None,
        per_ticket_timeout_sec: float = 180.0,
    ) -> None:
        self._backend = backend
        self._concurrency = min(max(1, concurrency), 3)
        self._cache_lookup = cache_lookup
        self.per_ticket_timeout_sec = per_ticket_timeout_sec

    async def analyze_many(
        self,
        snapshots: list[dict[str, Any]],
        *,
        project_key: str,
        run_id: str,
        force: bool = False,
    ) -> AnalysisDispatchResult:
        started_at = time.perf_counter()
        semaphore = asyncio.Semaphore(self._concurrency)

        async def run_one(snapshot: dict[str, Any]) -> AnalysisOutcome:
            async with semaphore:
                return await self._analyze_one(
                    snapshot,
                    project_key=project_key,
                    run_id=run_id,
                    force=force,
                )

        outcomes = await asyncio.gather(*(run_one(snapshot) for snapshot in snapshots))
        summary = AnalysisDispatchSummary(
            backend=self._backend.name,
            concurrency=self._concurrency,
            success=sum(1 for outcome in outcomes if outcome.status == "success"),
            cached=sum(1 for outcome in outcomes if outcome.status == "cached"),
            failed=sum(1 for outcome in outcomes if outcome.status == "failed"),
            skipped=sum(1 for outcome in outcomes if outcome.status == "skipped"),
            forced=force,
            duration_ms=_elapsed_ms(started_at),
            items=outcomes,
        )
        return AnalysisDispatchResult(outcomes=outcomes, summary=summary)

    async def _analyze_one(
        self,
        snapshot: dict[str, Any],
        *,
        project_key: str,
        run_id: str,
        force: bool,
    ) -> AnalysisOutcome:
        started_at = time.perf_counter()
        jira_key = str(snapshot.get("key") or "").strip()
        analysis_input_hash = build_analysis_input_hash(snapshot, project_key=project_key)
        if not jira_key:
            return AnalysisOutcome(
                jira_key="",
                status="skipped",
                analysis_input_hash=analysis_input_hash,
                duration_ms=_elapsed_ms(started_at),
                error="Missing Jira key",
                backend=self._backend.name,
            )

        if not force:
            cache_entry = await self._lookup_cache(jira_key)
            if cache_entry and cache_entry.analysis_input_hash == analysis_input_hash and cache_entry.analysis:
                return AnalysisOutcome(
                    jira_key=jira_key,
                    status="cached",
                    analysis_input_hash=analysis_input_hash,
                    duration_ms=_elapsed_ms(started_at),
                    analysis=cache_entry.analysis,
                    backend=self._backend.name,
                )

        try:
            analysis = await self._run_backend(snapshot, project_key=project_key, run_id=run_id)
        except asyncio.TimeoutError:
            return AnalysisOutcome(
                jira_key=jira_key,
                status="failed",
                analysis_input_hash=analysis_input_hash,
                duration_ms=_elapsed_ms(started_at),
                error=f"Analysis timed out after {self.per_ticket_timeout_sec:g}s",
                backend=self._backend.name,
            )
        except Exception as exc:
            return AnalysisOutcome(
                jira_key=jira_key,
                status="failed",
                analysis_input_hash=analysis_input_hash,
                duration_ms=_elapsed_ms(started_at),
                error=str(exc),
                backend=self._backend.name,
            )

        if analysis.get("readinessStatus") == "analysis_failed":
            return AnalysisOutcome(
                jira_key=jira_key,
                status="failed",
                analysis_input_hash=analysis_input_hash,
                duration_ms=_elapsed_ms(started_at),
                error=_analysis_failure_error(analysis),
                backend=self._backend.name,
            )

        analysis.setdefault("jiraSnapshot", snapshot)
        return AnalysisOutcome(
            jira_key=jira_key,
            status="success",
            analysis_input_hash=analysis_input_hash,
            duration_ms=_elapsed_ms(started_at),
            analysis=analysis,
            backend=self._backend.name,
        )

    async def _lookup_cache(self, jira_key: str) -> AnalysisCacheEntry | None:
        if self._cache_lookup is None:
            return None

        cache_entry = self._cache_lookup(jira_key)
        if inspect.isawaitable(cache_entry):
            return await cache_entry
        return cache_entry

    async def _run_backend(
        self,
        snapshot: dict[str, Any],
        *,
        project_key: str,
        run_id: str,
    ) -> dict[str, Any]:
        task = self._backend.analyze_ticket(snapshot, project_key=project_key, run_id=run_id)
        return await asyncio.wait_for(task, timeout=self.per_ticket_timeout_sec)


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _analysis_failure_error(analysis: dict[str, Any]) -> str:
    blockers = analysis.get("blockers")
    if isinstance(blockers, list):
        for blocker in blockers:
            if isinstance(blocker, str) and blocker.strip():
                return blocker.strip()
            if isinstance(blocker, dict):
                for key in ("message", "summary", "description", "error"):
                    value = blocker.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()

    summary = analysis.get("analysisSummary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return "LLM analysis failed before producing a valid readiness result."
