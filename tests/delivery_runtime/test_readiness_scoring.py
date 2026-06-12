"""Tests for readiness scoring heuristics."""

from delivery_runtime.readiness.scoring import score_ticket


def _snapshot(**overrides):
    base = {
        "key": "AAC-123",
        "summary": "Add OAuth callback handling",
        "description": (
            "Acceptance criteria:\n"
            "Given a signed-in user\n"
            "When OAuth completes\n"
            "Then the desktop stores the token"
        ),
        "status": "To Do",
        "issueType": "Story",
        "projectKey": "AAC",
    }
    base.update(overrides)
    return base


def test_score_ready_ticket():
    result = score_ticket(_snapshot(), recommended_repos=["gitlab.com/org/app"])
    assert result.score >= 70
    assert result.status == "ready"
    assert result.blockers == []
    assert result.recommended_repos == ["gitlab.com/org/app"]


def test_score_not_ready_without_acceptance_criteria():
    result = score_ticket(
        _snapshot(description="Implement OAuth callback handling soon."),
        recommended_repos=["gitlab.com/org/app"],
    )
    assert result.status == "not_ready"
    assert any("Acceptance criteria" in blocker for blocker in result.blockers)


def test_score_not_ready_without_repository():
    result = score_ticket(_snapshot())
    assert result.status == "not_ready"
    assert any("repository" in blocker.lower() for blocker in result.blockers)


def test_score_not_ready_for_blocked_ticket():
    result = score_ticket(
        _snapshot(status="Blocked"),
        recommended_repos=["gitlab.com/org/app"],
    )
    assert result.status == "not_ready"
    assert any("blocked" in blocker.lower() for blocker in result.blockers)
