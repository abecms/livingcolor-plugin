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
