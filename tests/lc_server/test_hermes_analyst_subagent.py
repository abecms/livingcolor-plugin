from __future__ import annotations

import pytest

from delivery_runtime.readiness.analyst_backend import SynchronousAnalystBackend
from lc_server.agent_bridge import hermes_analyst_subagent as subagent_module
from lc_server.agent_bridge.hermes_analyst_subagent import (
    HermesSubagentAnalystBackend,
    _extract_subagent_final_response,
    default_subagent_launcher_available,
)
from lc_server.factory import _build_readiness_analysis_backend


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


def test_extract_subagent_final_response_accepts_dict_shapes():
    assert _extract_subagent_final_response({"final_response": "snake"}) == "snake"
    assert _extract_subagent_final_response({"finalResponse": "camel"}) == "camel"
    assert _extract_subagent_final_response("plain") == "plain"
    assert _extract_subagent_final_response(None) == ""


def test_default_subagent_launcher_available_returns_false_without_module(monkeypatch):
    monkeypatch.setattr(subagent_module.importlib.util, "find_spec", lambda name: None)

    assert default_subagent_launcher_available() is False


@pytest.mark.asyncio
async def test_subagent_backend_uses_fallback_when_project_is_not_ready():
    calls = []

    async def fake_launcher(*, task_id: str, prompt: str, project_key: str) -> str:
        raise AssertionError("native launcher should not run for unprovisioned projects")

    def fallback_runner(snapshot: dict, project_key: str) -> dict:
        calls.append({"snapshot": snapshot, "project_key": project_key})
        return {
            "readinessScore": 42,
            "readinessStatus": "needs_clarification",
            "analysisSummary": "Fallback result.",
            "blockers": ["Missing details"],
            "recommendedRepos": [],
            "confidence": 0.42,
            "estimatedDays": 0,
            "jiraSnapshot": snapshot,
        }

    class _Registry:
        def is_automation_ready(self, project_key: str) -> bool:
            return False

    backend = HermesSubagentAnalystBackend(
        launcher=fake_launcher,
        fallback_runner=fallback_runner,
        registry=_Registry(),
    )

    result = await backend.analyze_ticket({"key": "TVP-2"}, project_key="TVP", run_id="DA-2")

    assert result["readinessStatus"] == "needs_clarification"
    assert calls == [{"snapshot": {"key": "TVP-2"}, "project_key": "TVP"}]


@pytest.mark.asyncio
async def test_subagent_backend_enriches_attachments_before_prompt(monkeypatch):
    prompts = []

    async def fake_launcher(*, task_id: str, prompt: str, project_key: str) -> str:
        prompts.append(prompt)
        return _completion()

    def enrich(snapshot: dict) -> dict:
        enriched = dict(snapshot)
        enriched["attachmentExtracts"] = [
            {
                "name": "screen.png",
                "mimeType": "image/png",
                "extractKind": "image_description",
                "content": "Observed modal error text.",
            }
        ]
        return enriched

    monkeypatch.setattr(subagent_module, "enrich_snapshot_with_attachment_extracts", enrich)

    backend = HermesSubagentAnalystBackend(launcher=fake_launcher)
    await backend.analyze_ticket(
        {
            "key": "TVP-3",
            "projectKey": "TVP",
            "summary": "Fix modal",
            "attachments": [{"name": "screen.png", "mimeType": "image/png"}],
        },
        project_key="TVP",
        run_id="DA-3",
    )

    assert "screen.png" in prompts[0]
    assert "Observed modal error text." in prompts[0]


def test_factory_uses_sync_backend_when_native_launcher_unavailable(monkeypatch):
    monkeypatch.setattr(
        "lc_server.factory.default_subagent_launcher_available",
        lambda: False,
    )

    backend = _build_readiness_analysis_backend()

    assert isinstance(backend, SynchronousAnalystBackend)


def test_factory_uses_subagent_backend_when_native_launcher_available(monkeypatch):
    monkeypatch.setattr(
        "lc_server.factory.default_subagent_launcher_available",
        lambda: True,
    )

    backend = _build_readiness_analysis_backend()

    assert isinstance(backend, HermesSubagentAnalystBackend)
