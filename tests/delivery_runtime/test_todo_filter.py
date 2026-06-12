"""Tests for To Do ticket filtering in daily analysis."""

from __future__ import annotations

import pytest

from delivery_runtime.readiness.todo_filter import is_todo_ticket


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        ({"status": "To Do", "statusCategory": "To Do"}, True),
        ({"status": "À faire", "statusCategory": "To Do"}, True),
        ({"status": "Backlog", "statusCategory": "To Do"}, True),
        ({"status": "In Progress", "statusCategory": "In Progress"}, False),
        ({"status": "Done", "statusCategory": "Done"}, False),
        ({"status": "En cours", "statusCategory": "In Progress"}, False),
        ({"status": "À faire"}, True),
        ({"status": "Review"}, False),
        ({"status": "Rouvert", "statusCategory": "In Progress"}, True),
        ({"status": "Reopened", "statusCategory": "To Do"}, True),
        ({"status": "Re-opened", "statusCategory": "Indeterminate"}, True),
        ({"status": "Réouvert", "statusCategory": "In Progress"}, True),
        ({"status": "ROUVERT", "statusCategory": "In Progress"}, True),
    ],
)
def test_is_todo_ticket(snapshot, expected):
    assert is_todo_ticket(snapshot) is expected
