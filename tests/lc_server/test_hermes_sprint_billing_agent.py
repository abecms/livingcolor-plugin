"""Tests for the Hermes sprint billing agent."""

from __future__ import annotations

from dataclasses import dataclass

from lc_server.agent_bridge.hermes_sprint_billing import HermesSprintBillingAgent


def test_sprint_billing_agent_returns_json_proposal(monkeypatch):
    prompts: list[str] = []

    @dataclass
    class CapturingAgent:
        def run_conversation(self, prompt: str, *, task_id: str):
            prompts.append(prompt)
            return {
                "final_response": """
```json
{
  "customerId": "cus_123",
  "currency": "eur",
  "lineItems": [
    {
      "description": "Delivered BN-1",
      "ticketKeys": ["BN-1"],
      "quantityDays": 2.0,
      "unitAmountCents": 80000
    }
  ],
  "memo": "Sprint 12 delivery invoice",
  "warnings": []
}
```
"""
            }

    agent = HermesSprintBillingAgent(agent_factory=lambda **kwargs: CapturingAgent())
    proposal = agent.propose(
        {
            "projectKey": "BN",
            "sprintNumber": 12,
            "dedupKey": "12:2026-06-30",
            "customerId": "cus_123",
            "currency": "eur",
            "dailyRateCents": 80000,
            "deliveredTickets": [{"jiraKey": "BN-1", "title": "Delivered", "estimatedDays": 2.0}],
        },
        project_key="BN",
    )

    assert proposal["customerId"] == "cus_123"
    assert proposal["lineItems"][0]["ticketKeys"] == ["BN-1"]
    assert "Output ONLY valid JSON" in prompts[0]
    assert "cus_123" in prompts[0]
