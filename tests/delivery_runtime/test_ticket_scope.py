"""Tests for configurable ticket scope filtering."""

from __future__ import annotations

import pytest

from delivery_runtime.readiness.ticket_scope import (
    TicketScopeConfig,
    build_ticket_scope_jql_variants,
    matches_ticket_scope,
    needs_broad_jira_fetch,
    parse_ticket_scope,
)


@pytest.mark.parametrize(
    ("snapshot", "scope", "expected"),
    [
        ({"status": "To Do", "statusCategory": "To Do"}, TicketScopeConfig(), True),
        ({"status": "In Progress", "statusCategory": "In Progress"}, TicketScopeConfig(), False),
        (
            {"status": "In Progress", "statusCategory": "In Progress", "assignee": "Ada Lovelace"},
            TicketScopeConfig(status_groups=("in_progress",)),
            True,
        ),
        (
            {"status": "Done", "statusCategory": "Done", "assignee": "Ada Lovelace"},
            TicketScopeConfig(status_groups=(), assignees=("Ada Lovelace",)),
            True,
        ),
        (
            {"status": "To Do", "statusCategory": "To Do", "assignee": "Bob"},
            TicketScopeConfig(status_groups=("todo",), assignees=("Ada Lovelace",)),
            False,
        ),
        (
            {"status": "To Do", "statusCategory": "To Do", "assignee": "Ada Lovelace"},
            TicketScopeConfig(
                status_groups=("todo",),
                assignees=("Ada Lovelace",),
                match_mode="all",
            ),
            True,
        ),
        (
            {"status": "Done", "statusCategory": "Done", "assignee": "Ada Lovelace"},
            TicketScopeConfig(
                status_groups=("todo",),
                assignees=("Ada Lovelace",),
                match_mode="any",
            ),
            True,
        ),
        (
            {"status": "To Do", "statusCategory": "To Do", "assignee": "Unassigned"},
            TicketScopeConfig(status_groups=("todo",), assignees=("Ada Lovelace",), include_unassigned=False),
            False,
        ),
        (
            {"status": "To Do", "statusCategory": "To Do", "assignee": "Grégory Besson"},
            TicketScopeConfig(status_groups=("todo",), assignees=("Gregory Besson",), match_mode="all"),
            True,
        ),
        (
            {
                "status": "To Do",
                "statusCategory": "To Do",
                "assignee": "tamsi.besson@example.com",
                "assigneeEmail": "tamsi.besson@example.com",
            },
            TicketScopeConfig(status_groups=("todo",), assignees=("Tamsi Besson",), match_mode="all"),
            True,
        ),
    ],
)
def test_matches_ticket_scope(snapshot, scope, expected):
    assert matches_ticket_scope(snapshot, scope) is expected


def test_parse_ticket_scope_defaults():
    scope = parse_ticket_scope(None)
    assert scope.status_groups == ("todo",)
    assert scope.assignees == ()
    assert scope.match_mode == "all"


def test_parse_ticket_scope_excludes_unassigned_when_assignees_set():
    scope = parse_ticket_scope(
        {
            "statusGroups": ["todo"],
            "assignees": ["Tamsi Besson"],
        }
    )
    assert scope.include_unassigned is False


def test_unassigned_ticket_excluded_when_assignee_filter_without_unassigned():
    snapshot = {"status": "To Do", "statusCategory": "To Do", "assignee": "Unassigned"}
    scope = TicketScopeConfig(
        status_groups=("todo",),
        assignees=("Tamsi Besson",),
        include_unassigned=False,
        match_mode="all",
    )
    assert matches_ticket_scope(snapshot, scope) is False


def test_build_ticket_scope_jql_includes_assignee_filter():
    scope = TicketScopeConfig(
        status_groups=("todo",),
        assignees=("Tamsi Besson", "Grégory Besson"),
        include_unassigned=False,
        match_mode="all",
    )
    variants = build_ticket_scope_jql_variants("TVP", scope)
    assert len(variants) == 2
    assert 'assignee in ("Tamsi Besson", "Grégory Besson")' in variants[0]
    assert "statusCategory = \"To Do\"" in variants[0]
    assert "Rouvert" in variants[0]
    assert "ROUVERT" in variants[0]
    assert "À FAIRE" in variants[0]


def test_build_ticket_scope_jql_includes_french_todo_statuses():
    scope = TicketScopeConfig(status_groups=("todo",))
    variants = build_ticket_scope_jql_variants("TVP", scope)
    assert "À FAIRE" in variants[0]
    assert "ROUVERT" in variants[0]


def test_needs_broad_jira_fetch():
    assert needs_broad_jira_fetch(TicketScopeConfig(status_groups=("todo",))) is False
    assert needs_broad_jira_fetch(TicketScopeConfig(status_groups=("in_progress",))) is False
    assert needs_broad_jira_fetch(TicketScopeConfig(assignees=("Ada",))) is False
    assert (
        needs_broad_jira_fetch(
            TicketScopeConfig(status_groups=("todo",), assignees=("Ada Lovelace",))
        )
        is False
    )
