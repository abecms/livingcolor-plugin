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


class SlowBackend:
    name = "slow"

    async def analyze_ticket(self, snapshot: dict[str, Any], *, project_key: str, run_id: str) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return _analysis(snapshot)


class SnapshotlessBackend:
    name = "snapshotless"

    async def analyze_ticket(self, snapshot: dict[str, Any], *, project_key: str, run_id: str) -> dict[str, Any]:
        return {
            "readinessScore": 82,
            "readinessStatus": "ready",
            "analysisSummary": f"{snapshot['key']} is ready.",
            "blockers": [],
            "recommendedRepos": ["tv5monde/tv5mondeplus-front"],
            "confidence": 0.82,
            "estimatedDays": 1.0,
        }


class AnalysisFailedBackend:
    name = "analysis-failed"

    async def analyze_ticket(self, snapshot: dict[str, Any], *, project_key: str, run_id: str) -> dict[str, Any]:
        return {
            "readinessScore": 0,
            "readinessStatus": "analysis_failed",
            "analysisSummary": "Could not parse analyst response.",
            "blockers": ["Analyst returned invalid JSON"],
            "recommendedRepos": [],
            "confidence": 0,
            "estimatedDays": None,
            "jiraSnapshot": snapshot,
        }


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
    assert result.outcomes[0].backend == "recording"


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


@pytest.mark.asyncio
async def test_summary_to_dict_uses_spec_shape_with_durations():
    backend = RecordingBackend()
    dispatcher = ReadinessAnalysisDispatcher(backend=backend, concurrency=10)
    result = await dispatcher.analyze_many([_snapshot("TVP-1")], project_key="TVP", run_id="DA-1", force=True)

    summary = result.summary.to_dict()

    assert summary["backend"] == "recording"
    assert summary["concurrency"] == 3
    assert summary["forced"] is True
    assert "durationMs" in summary
    assert summary["items"][0]["jiraKey"] == "TVP-1"
    assert summary["items"][0]["backend"] == "recording"
    assert "durationMs" in summary["items"][0]


@pytest.mark.asyncio
async def test_dispatcher_times_out_slow_backend():
    dispatcher = ReadinessAnalysisDispatcher(
        backend=SlowBackend(),
        concurrency=3,
        per_ticket_timeout_sec=0.001,
    )

    result = await dispatcher.analyze_many([_snapshot("TVP-1")], project_key="TVP", run_id="DA-1", force=True)

    assert result.summary.failed == 1
    assert result.outcomes[0].status == "failed"
    assert result.outcomes[0].error


@pytest.mark.asyncio
async def test_dispatcher_skips_snapshot_without_jira_key():
    backend = RecordingBackend()
    dispatcher = ReadinessAnalysisDispatcher(
        backend=backend,
        concurrency=3,
        cache_lookup=lambda jira_key: pytest.fail("cache should not be called"),
    )
    snapshot = _snapshot("")

    result = await dispatcher.analyze_many([snapshot], project_key="TVP", run_id="DA-1", force=False)

    assert result.summary.skipped == 1
    assert result.summary.success == 0
    assert result.outcomes[0].status == "skipped"
    assert result.outcomes[0].analysis_input_hash == build_analysis_input_hash(snapshot, project_key="TVP")
    assert backend.calls == []


@pytest.mark.asyncio
async def test_dispatcher_ignores_cache_entry_without_analysis():
    backend = RecordingBackend()
    snapshot = _snapshot("TVP-1")
    input_hash = build_analysis_input_hash(snapshot, project_key="TVP")
    dispatcher = ReadinessAnalysisDispatcher(
        backend=backend,
        concurrency=3,
        cache_lookup=lambda jira_key: AnalysisCacheEntry(
            jira_key=jira_key,
            analysis_input_hash=input_hash,
            analysis=None,
        ),
    )

    result = await dispatcher.analyze_many([snapshot], project_key="TVP", run_id="DA-1", force=False)

    assert result.summary.cached == 0
    assert result.summary.success == 1
    assert backend.calls == ["TVP-1"]


def test_analysis_input_hash_normalizes_project_key_and_uses_fallback_fields():
    base = {
        "key": "TVP-1",
        "title": "Fallback title",
        "description": "Acceptance criteria: render the page.",
        "issue_type": "Task",
        "status": "To Do",
        "statusCategory": "To Do",
        "labels": ["front"],
        "assigneeDisplayName": "Ada Lovelace",
        "assigneeEmail": "ada@example.com",
        "comments": [],
        "attachments": [],
        "attachmentExtracts": [],
    }

    normalized = build_analysis_input_hash(base, project_key=" tvp ")
    upper = build_analysis_input_hash(base, project_key="TVP")
    changed_title = build_analysis_input_hash({**base, "title": "Changed title"}, project_key="TVP")
    changed_issue_type = build_analysis_input_hash({**base, "issue_type": "Bug"}, project_key="TVP")

    assert normalized == upper
    assert changed_title != normalized
    assert changed_issue_type != normalized


def test_analysis_input_hash_treats_none_list_fields_as_empty_lists():
    missing_lists = {
        "key": "TVP-1",
        "summary": "Ticket TVP-1",
        "description": "Acceptance criteria: render the page.",
        "issueType": "Task",
        "status": "To Do",
        "statusCategory": "To Do",
    }
    none_lists = {
        **missing_lists,
        "labels": None,
        "comments": None,
        "attachments": None,
        "attachmentExtracts": None,
    }
    empty_lists = {
        **missing_lists,
        "labels": [],
        "comments": [],
        "attachments": [],
        "attachmentExtracts": [],
    }

    assert build_analysis_input_hash(none_lists, project_key="TVP") == build_analysis_input_hash(
        missing_lists,
        project_key="TVP",
    )
    assert build_analysis_input_hash(empty_lists, project_key="TVP") == build_analysis_input_hash(
        missing_lists,
        project_key="TVP",
    )


@pytest.mark.asyncio
async def test_dispatcher_adds_missing_jira_snapshot_to_successful_analysis():
    snapshot = _snapshot("TVP-1")
    dispatcher = ReadinessAnalysisDispatcher(backend=SnapshotlessBackend(), concurrency=3)

    result = await dispatcher.analyze_many([snapshot], project_key="TVP", run_id="DA-1", force=True)

    assert result.summary.success == 1
    assert result.outcomes[0].analysis is not None
    assert result.outcomes[0].analysis["jiraSnapshot"] == snapshot


@pytest.mark.asyncio
async def test_dispatcher_treats_analysis_failed_payload_as_failed_outcome():
    snapshot = _snapshot("TVP-1")
    dispatcher = ReadinessAnalysisDispatcher(backend=AnalysisFailedBackend(), concurrency=3)

    result = await dispatcher.analyze_many([snapshot], project_key="TVP", run_id="DA-1", force=True)

    assert result.summary.failed == 1
    assert result.summary.success == 0
    outcome = result.outcomes[0]
    assert outcome.status == "failed"
    assert outcome.analysis is None
    assert outcome.analysis_input_hash == build_analysis_input_hash(snapshot, project_key="TVP")
    assert outcome.backend == "analysis-failed"
    assert outcome.error == "Analyst returned invalid JSON"
