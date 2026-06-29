"""Tests for heuristic sprint billing proposal."""

from __future__ import annotations

from lc_server.agent_bridge.heuristic_sprint_billing import propose_heuristic_sprint_billing


def test_propose_heuristic_sprint_billing_builds_line_items():
    snapshot = {
        "customerId": "cus_test",
        "currency": "eur",
        "dailyRateCents": 80000,
        "sprintNumber": 3,
        "doneTickets": [{"jiraKey": "TVP-14", "title": "Example", "estimatedDays": 1.0}],
    }
    proposal = propose_heuristic_sprint_billing(snapshot, project_key="TVP")
    assert proposal["customerId"] == "cus_test"
    assert proposal["currency"] == "eur"
    assert proposal["totalCents"] == 80000
    assert proposal["lineItems"][0]["ticketKeys"] == ["TVP-14"]
