"""Tests for LivingColor sprint selection helpers."""

from delivery_runtime.pm_inbox.sprint import build_sprint_recommendation


def test_sprint_selection_respects_capacity():
    recommendation = build_sprint_recommendation(
        project_key="BN",
        candidates=[
            {
                "readinessId": "RD-1",
                "jiraKey": "BN-1",
                "title": "Small",
                "estimatedDays": 1.0,
                "jiraSnapshot": {"priority": "High"},
            },
            {
                "readinessId": "RD-2",
                "jiraKey": "BN-2",
                "title": "Large",
                "estimatedDays": 3.0,
                "jiraSnapshot": {"priority": "High"},
            },
        ],
        capacity_days=2,
        duration_days=14,
    )

    assert recommendation.sprint_name == "LivingColor Sprint"
    assert recommendation.capacity_days == 2
    assert len(recommendation.tickets) == 1
    assert recommendation.tickets[0].jira_key == "BN-1"
    assert recommendation.overflow_risk is True
