"""Tests for LLM Gate 1 planner prompt parsing and Hermes planner agent."""

from __future__ import annotations

import json

import pytest

from delivery_runtime.context.models import ContextPack
from delivery_runtime.context.planner_prompt import (
    PlannerParseError,
    build_planner_user_prompt,
    parse_planner_completion,
)


def _sample_pack() -> ContextPack:
    return ContextPack(
        jira_key="TVP-1489",
        jira_ticket={
            "key": "TVP-1489",
            "summary": "[WEB] [SEO] Guide TV - Problème rendering",
            "description": "La grille guide TV n'apparaît pas dans le HTML initial.",
            "projectKey": "TVP",
            "issueType": "Bug",
        },
        acceptance_criteria=["Guide TV grid is present in server-rendered HTML."],
        identified_repo="tv5monde/tv5mondeplus-front",
        candidate_files=["tests/unit/live-direct-name.test.js", "assets/js/tv-guide.js"],
        jira_attachment_extracts=[
            {
                "name": "Rendu de la page Guide (1).pdf",
                "extractKind": "pdf_text",
                "content": "Optimisation Guide TV\nRendering\nSolutions possibles",
            }
        ],
    )


def _completion_text(payload: dict) -> str:
    return "Plan summary\n```json\n" + json.dumps(payload) + "\n```"


def test_build_planner_user_prompt_warns_about_heuristic_candidates():
    prompt = build_planner_user_prompt(_sample_pack())

    assert "Heuristic candidate files" in prompt
    assert "Do not pick the top candidate blindly" in prompt
    assert "tv-guide.js" in prompt
    assert "Rendering" in prompt


def test_parse_planner_completion_extracts_gate1_payload():
    pack = _sample_pack()
    payload = {
        "needsClarification": False,
        "ticketUnderstanding": "SSR missing for Guide TV grid.",
        "targetRepo": "tv5monde/tv5mondeplus-front",
        "implementationPlan": "1. Inspect tv-guide template\n2. Add SSR",
        "likelyImpactedFiles": ["assets/js/tv-guide.js", "templates/tv-guide.html.twig"],
        "risks": ["Regression on client hydration"],
        "confidenceLevel": 0.82,
    }

    result = parse_planner_completion(_completion_text(payload), pack)

    assert result["needsClarification"] is False
    assert result["targetRepo"] == "tv5monde/tv5mondeplus-front"
    assert "tv-guide.js" in result["likelyImpactedFiles"][0]
    assert result["confidenceLevel"] == 0.82
    assert result["contextPack"]["jira_key"] == "TVP-1489"


def test_parse_planner_completion_clarification_path():
    pack = _sample_pack()
    payload = {
        "needsClarification": True,
        "clarificationReason": "No repository mapped.",
    }

    result = parse_planner_completion(_completion_text(payload), pack)

    assert result["needsClarification"] is True
    assert "repository" in result["clarificationReason"].lower()


def test_parse_planner_completion_rejects_wildcard_paths():
    pack = _sample_pack()
    payload = {
        "needsClarification": False,
        "ticketUnderstanding": "x",
        "targetRepo": "group/repo",
        "implementationPlan": "1. x",
        "likelyImpactedFiles": ["src/**"],
        "risks": [],
        "confidenceLevel": 0.5,
    }

    with pytest.raises(PlannerParseError, match="wildcard"):
        parse_planner_completion(_completion_text(payload), pack)


def test_parse_planner_completion_raises_on_missing_json():
    with pytest.raises(PlannerParseError, match="missing a JSON block"):
        parse_planner_completion("No JSON here", _sample_pack())


def test_hermes_planner_agent_uses_mock_factory():
    from lc_server.agent_bridge.hermes_planner import HermesPlannerAgent

    pack = _sample_pack()
    captured: dict[str, object] = {}

    class _FakeAgent:
        def run_conversation(self, prompt: str, task_id: str | None = None) -> dict:
            captured["prompt"] = prompt
            captured["task_id"] = task_id
            return {
                "final_response": _completion_text(
                    {
                        "needsClarification": False,
                        "ticketUnderstanding": "Fix SSR for Guide TV.",
                        "targetRepo": "tv5monde/tv5mondeplus-front",
                        "implementationPlan": "1. Update twig template",
                        "likelyImpactedFiles": ["assets/js/tv-guide.js"],
                        "risks": ["SEO regression"],
                        "confidenceLevel": 0.9,
                    }
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

    agent = HermesPlannerAgent(agent_factory=factory, registry=_Registry())
    result = agent.plan(pack, project_key="TVP")

    assert result["needsClarification"] is False
    assert "tv-guide.js" in result["likelyImpactedFiles"][0]
    assert captured["task_id"] == "delivery-planner-TVP-1489"
    assert "TVP-1489" in str(captured["prompt"])
    assert captured["factory_kwargs"]["project_key"] == "TVP"


@pytest.mark.asyncio
async def test_implementation_plan_node_delegates_to_llm_planner():
    from lc_server.agent_bridge.hermes_runtime import HermesRuntimeBridge

    expected = {
        "needsClarification": False,
        "targetRepo": "tv5monde/tv5mondeplus-front",
        "likelyImpactedFiles": ["assets/js/tv-guide.js"],
        "implementationPlan": "1. SSR",
        "ticketUnderstanding": "Guide TV SSR",
        "risks": [],
        "confidenceLevel": 0.8,
        "contextPack": {},
    }

    class _FakePlanner:
        def plan(self, pack, *, project_key: str) -> dict:
            assert pack.jira_key == "TVP-1489"
            assert project_key == "TVP"
            return expected

    bridge = HermesRuntimeBridge(planner=_FakePlanner())
    result = await bridge.run_node(
        "WO-52",
        {"nodeType": "implementation_plan", "payload": {}},
        {
            "projectKey": "TVP",
            "workOrder": {"jiraKey": "TVP-1489", "projectKey": "TVP"},
            "jiraSnapshot": {
                "key": "TVP-1489",
                "summary": "Guide TV rendering",
                "projectKey": "TVP",
            },
        },
    )

    assert result == expected
