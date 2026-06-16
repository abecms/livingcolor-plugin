from __future__ import annotations

import json

import pytest

from delivery_runtime.readiness.analyst_prompt import (
    AnalystParseError,
    build_analyst_user_prompt,
    parse_analyst_completion,
)


def _payload(**overrides):
    payload = {
        "readinessScore": 82,
        "readinessStatus": "ready",
        "analysisSummary": "The ticket has enough technical detail for implementation.",
        "blockers": [],
        "recommendedRepos": ["tv5monde/tv5mondeplus-front"],
        "confidence": 0.82,
        "estimatedDays": 1.5,
    }
    payload.update(overrides)
    return payload


def _fenced(payload: dict) -> str:
    return "```json\n" + json.dumps(payload) + "\n```"


@pytest.mark.parametrize(
    "status",
    ["needs_clarification", "not_development", "analysis_failed"],
)
def test_parse_analyst_completion_accepts_runtime_statuses(status):
    result = parse_analyst_completion(_fenced(_payload(readinessStatus=status)), {"key": "TVP-1"})

    assert result["readinessStatus"] == status


def test_parse_analyst_completion_handles_fenced_json():
    result = parse_analyst_completion(_fenced(_payload()), {"key": "TVP-2"})

    assert result["readinessStatus"] == "ready"
    assert result["estimatedDays"] == 1.5


def test_parse_analyst_completion_handles_raw_json():
    result = parse_analyst_completion(json.dumps(_payload(readinessStatus="not_ready")), {"key": "TVP-3"})

    assert result["readinessStatus"] == "not_ready"


def test_parse_analyst_completion_rejects_missing_json():
    with pytest.raises(AnalystParseError, match="missing a JSON block"):
        parse_analyst_completion("No structured readiness result.", {"key": "TVP-4"})


def test_parse_analyst_completion_rejects_invalid_status():
    with pytest.raises(AnalystParseError, match="readinessStatus"):
        parse_analyst_completion(_fenced(_payload(readinessStatus="ambiguous")), {"key": "TVP-5"})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("readinessScore", True, "readinessScore must be numeric"),
        ("confidence", False, "confidence must be numeric"),
        ("blockers", "missing API contract", "blockers must be a list"),
        ("recommendedRepos", "tv5monde/tv5mondeplus-front", "recommendedRepos must be a list"),
    ],
)
def test_parse_analyst_completion_rejects_invalid_field_types(field, value, message):
    with pytest.raises(AnalystParseError, match=message):
        parse_analyst_completion(_fenced(_payload(**{field: value})), {"key": "TVP-6"})


def test_build_analyst_user_prompt_contains_livingcolor_readiness_semantics():
    prompt = build_analyst_user_prompt(
        {
            "key": "TVP-2391",
            "projectKey": "TVP",
            "summary": "Add schema.org FAQPage JSON-LD on film category pages",
            "description": "Add JSON-LD blocks for FAQPage on /films pages with the exact properties listed.",
            "issueType": "Task",
            "status": "To Do",
        }
    )
    lowered = prompt.lower()

    assert "ready: implementation can start from the ticket and available repo context" in lowered
    assert "not_ready: ticket is blocked by missing technical information" in lowered
    assert "needs_clarification: genuine product/ux/business ambiguity" in lowered
    assert "not_development: request is not implementation work" in lowered
    assert "analysis_failed: reserved for runtime failures" in lowered
    assert "technical tickets can be ready" in lowered
    assert "not written as user stories" in lowered
    assert "schema.org" in lowered
