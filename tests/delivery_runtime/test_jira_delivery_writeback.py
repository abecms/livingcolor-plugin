"""Tests for Jira delivery write-back helpers."""

from delivery_runtime.jira.delivery_writeback import write_delivery_completion_to_jira
from lc_server.integrations.jira_delivery_invoker import pick_transition_id


class FakeJiraDeliveryInvoker:
    def __init__(self) -> None:
        self.comments: list[tuple[str, str]] = []
        self.transition_calls: list[tuple[str, str]] = []
        self._transitions_by_issue: dict[str, list[dict]] = {
            "TVP-1": [
                {"id": "6", "name": "Start"},
            ],
            "TVP-2": [
                {"id": "15", "name": "To Test Internally"},
            ],
        }

    def add_comment(self, issue_key: str, body: str) -> dict:
        self.comments.append((issue_key, body))
        return {"id": "1"}

    def list_transitions(self, issue_key: str) -> list[dict]:
        return list(self._transitions_by_issue.get(issue_key, []))

    def transition_issue(self, issue_key: str, *, transition_id: str) -> dict:
        self.transition_calls.append((issue_key, transition_id))
        if issue_key == "TVP-1" and transition_id == "6":
            self._transitions_by_issue["TVP-1"] = [{"id": "15", "name": "To Test Internally"}]
            return {"ok": True}
        return {"ok": True}


def test_pick_transition_id_matches_preferred_name():
    transitions = [{"id": "15", "name": "To Test Internally"}, {"id": "4", "name": "CANCELED"}]
    assert pick_transition_id(transitions, preferred_names=["Test", "To Test Internally"]) == "15"


def test_write_delivery_completion_posts_comment_and_transitions(monkeypatch):
    invoker = FakeJiraDeliveryInvoker()

    def fake_resolve(project_key: str | None) -> list[str]:
        return ["To Test Internally", "Test"]

    monkeypatch.setattr(
        "delivery_runtime.jira.delivery_writeback.resolve_delivery_transition_names",
        fake_resolve,
    )

    result = write_delivery_completion_to_jira(
        "TVP-2",
        "Merge request: https://example.com/mr/1",
        project_key="TVP",
        invoker=invoker,
    )

    assert result["commentPosted"] is True
    assert result["transitionApplied"] is True
    assert invoker.comments == [("TVP-2", "Merge request: https://example.com/mr/1")]
    assert invoker.transition_calls == [("TVP-2", "15")]
