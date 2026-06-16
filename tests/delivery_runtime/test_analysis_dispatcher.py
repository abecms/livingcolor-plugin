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
