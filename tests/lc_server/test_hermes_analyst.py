"""Tests for Hermes-backed analyst readiness analysis."""

from __future__ import annotations

import json

import pytest

from delivery_runtime.readiness.analyst_prompt import AnalystParseError, build_analyst_user_prompt, parse_analyst_completion

_BASE_COMPLETION = {
    "readinessScore": 80,
    "readinessStatus": "ready",
    "analysisSummary": "Looks good",
    "blockers": [],
    "recommendedRepos": ["tv5mondeplus-front"],
    "confidence": 0.8,
    "estimatedDays": 1.0,
}


def _completion_text(payload: dict) -> str:
    return "Summary here\n```json\n" + json.dumps(payload) + "\n```"


def test_parse_analyst_completion_extracts_json_block():
    text = (
        "Summary here\n"
        "```json\n"
        '{"readinessScore": 82, "readinessStatus": "ready", "analysisSummary": "OK", '
        '"blockers": [], "recommendedRepos": ["group/bn-frontend"], "confidence": 0.9, '
        '"estimatedDays": 1}\n'
        "```"
    )
    snapshot = {"key": "BN-1", "projectKey": "BN"}

    result = parse_analyst_completion(text, snapshot)

    assert result["readinessScore"] == 82
    assert result["readinessStatus"] == "ready"
    assert result["analysisSummary"] == "OK"
    assert result["recommendedRepos"] == ["group/bn-frontend"]
    assert result["confidence"] == 0.9
    assert result["jiraSnapshot"]["key"] == "BN-1"


def test_parse_analyst_completion_extracts_estimated_days():
    payload = {**_BASE_COMPLETION, "estimatedDays": 1.5}
    result = parse_analyst_completion(_completion_text(payload), {})
    assert result["estimatedDays"] == 1.5


def test_parse_analyst_completion_rejects_missing_estimated_days():
    payload = dict(_BASE_COMPLETION)
    payload.pop("estimatedDays")

    with pytest.raises(AnalystParseError, match="estimatedDays"):
        parse_analyst_completion(_completion_text(payload), {})


def test_parse_analyst_completion_ignores_invalid_estimated_days():
    payload = {**_BASE_COMPLETION, "estimatedDays": "soon"}
    with pytest.raises(AnalystParseError, match="estimatedDays"):
        parse_analyst_completion(_completion_text(payload), {})


def test_parse_analyst_completion_rejects_boolean_estimated_days():
    payload = {**_BASE_COMPLETION, "estimatedDays": True}
    with pytest.raises(AnalystParseError, match="estimatedDays"):
        parse_analyst_completion(_completion_text(payload), {})


def test_parse_analyst_completion_rejects_negative_estimated_days():
    payload = {**_BASE_COMPLETION, "estimatedDays": -2}
    with pytest.raises(AnalystParseError, match="estimatedDays"):
        parse_analyst_completion(_completion_text(payload), {})


def test_parse_analyst_completion_raises_on_missing_json():
    with pytest.raises(AnalystParseError, match="missing a JSON block"):
        parse_analyst_completion("No structured output", snapshot={"key": "BN-2"})


def test_parse_analyst_completion_accepts_extended_statuses():
    payload = {**_BASE_COMPLETION, "readinessStatus": "needs_clarification"}
    result = parse_analyst_completion(_completion_text(payload), {})
    assert result["readinessStatus"] == "needs_clarification"


def test_parse_analyst_completion_raises_on_invalid_status():
    text = (
        "```json\n"
        '{"readinessScore": 50, "readinessStatus": "maybe", "analysisSummary": "x", '
        '"blockers": [], "recommendedRepos": [], "confidence": 0.5, "estimatedDays": 1}\n'
        "```"
    )
    with pytest.raises(AnalystParseError, match="readinessStatus"):
        parse_analyst_completion(text, snapshot={"key": "BN-3"})


def test_build_analyst_user_prompt_includes_comments_and_reopened_context():
    snapshot = {
        "key": "TVP-7",
        "projectKey": "TVP",
        "summary": "Checkout bug",
        "description": "Initial scope",
        "status": "Reopened",
        "reanalyzeContext": True,
        "isReopened": True,
        "comments": [
            {
                "author": "PM",
                "body": "Sent back: missing edge case for guest checkout.",
                "created": "2026-06-11T08:00:00.000+0000",
            }
        ],
    }

    prompt = build_analyst_user_prompt(snapshot)

    assert "## Jira comments (mandatory input)" in prompt
    assert "Re-opened / re-analysis context" in prompt
    assert "Sent back: missing edge case for guest checkout." in prompt
    assert "source of truth" in prompt


@pytest.mark.asyncio
async def test_run_readiness_analysis_delegates_to_analyst_when_automation_ready():
    from lc_server.agent_bridge.hermes_runtime import HermesRuntimeBridge

    snapshot = {"key": "BN-9", "summary": "OAuth callback", "projectKey": "BN"}
    expected = {
        "readinessScore": 88,
        "readinessStatus": "ready",
        "analysisSummary": "Ready for delivery.",
        "blockers": [],
        "recommendedRepos": ["group/bn-frontend"],
        "confidence": 0.88,
        "jiraSnapshot": snapshot,
    }

    class _FakeRegistry:
        def is_automation_ready(self, project_key: str) -> bool:
            return project_key == "BN"

    class _FakeAnalyst:
        def analyze(self, received_snapshot: dict, project_key: str) -> dict:
            assert received_snapshot == snapshot
            assert project_key == "BN"
            return expected

    bridge = HermesRuntimeBridge(registry=_FakeRegistry(), analyst=_FakeAnalyst())
    result = await bridge.run_readiness_analysis("BN-9", {"projectKey": "BN", "snapshot": snapshot})

    assert result == expected


@pytest.mark.asyncio
async def test_run_readiness_analysis_returns_analysis_failed_on_parse_error():
    from lc_server.agent_bridge.hermes_runtime import HermesRuntimeBridge

    snapshot = {
        "key": "BN-10",
        "summary": "OAuth callback",
        "description": "Given a user completes OAuth, when the callback returns, then tokens are stored.",
        "projectKey": "BN",
    }

    class _FakeRegistry:
        def is_automation_ready(self, project_key: str) -> bool:
            return project_key == "BN"

    class _FailingAnalyst:
        def analyze(self, received_snapshot: dict, project_key: str) -> dict:
            assert received_snapshot == snapshot
            assert project_key == "BN"
            raise AnalystParseError("bad JSON")

    bridge = HermesRuntimeBridge(registry=_FakeRegistry(), analyst=_FailingAnalyst())
    result = await bridge.run_readiness_analysis("BN-10", {"projectKey": "BN", "snapshot": snapshot})

    assert result["readinessStatus"] == "analysis_failed"
    assert result["readinessScore"] == 0
    assert result["estimatedDays"] == 0
    assert result["recommendedRepos"] == []
    assert "could not be parsed" in result["analysisSummary"]
    assert result["blockers"] == ["bad JSON"]
    assert result["jiraSnapshot"] == snapshot


@pytest.mark.asyncio
async def test_run_readiness_analysis_falls_back_to_heuristic_when_not_provisioned():
    from delivery_runtime.readiness.analyzer import analyze_ticket_snapshot
    from lc_server.agent_bridge.hermes_runtime import HermesRuntimeBridge

    snapshot = {
        "key": "ZZ-1",
        "projectKey": "ZZ",
        "summary": "Add OAuth callback persistence",
        "description": "Given a user completes OAuth, when the callback returns, then tokens are stored.",
        "issueType": "Story",
        "status": "To Do",
    }

    class _FakeRegistry:
        def is_automation_ready(self, project_key: str) -> bool:
            return False

    class _FailAnalyst:
        def analyze(self, *_args, **_kwargs):
            raise AssertionError("analyst should not run when automation is not ready")

    bridge = HermesRuntimeBridge(registry=_FakeRegistry(), analyst=_FailAnalyst())
    result = await bridge.run_readiness_analysis("ZZ-1", {"projectKey": "ZZ", "snapshot": snapshot})

    assert result == analyze_ticket_snapshot(snapshot)


def test_hermes_analyst_agent_uses_mock_factory():
    from lc_server.agent_bridge.hermes_analyst import HermesAnalystAgent

    snapshot = {"key": "BN-4", "projectKey": "BN", "summary": "Ticket"}
    captured: dict[str, object] = {}

    class _FakeAgent:
        def run_conversation(self, prompt: str, task_id: str | None = None) -> dict:
            captured["prompt"] = prompt
            captured["task_id"] = task_id
            return {
                "final_response": (
                    "```json\n"
                    '{"readinessScore": 75, "readinessStatus": "ready", "analysisSummary": "Looks good", '
                    '"blockers": [], "recommendedRepos": ["group/repo"], "confidence": 0.75, '
                    '"estimatedDays": 1}\n'
                    "```"
                )
            }

    def factory(**kwargs):
        captured["factory_kwargs"] = kwargs
        return _FakeAgent()

    class _Registry:
        def is_automation_ready(self, project_key: str) -> bool:
            return True

        def get(self, project_key: str, role: str):
            return None

    agent = HermesAnalystAgent(agent_factory=factory, registry=_Registry())
    result = agent.analyze(snapshot, "BN")

    assert result["readinessScore"] == 75
    assert result["jiraSnapshot"] == snapshot
    assert captured["task_id"] == "delivery-analyst-BN-4"
    assert "BN-4" in str(captured["prompt"])
    assert captured["factory_kwargs"]["project_key"] == "BN"
