"""Tests for Jira readiness integration auto-reconnect."""

from __future__ import annotations

import pytest

from delivery_runtime.readiness.errors import ReadinessIntegrationError
from delivery_runtime.readiness.ticket_scope import TicketScopeConfig


def test_fetch_issues_for_readiness_reconnects_before_scanning(monkeypatch):
    ensure_calls: list[str] = []

    def fake_ensure():
        ensure_calls.append("ensure")

    monkeypatch.setattr(
        "hermes_cli.jira_dashboard.ensure_jira_mcp_connected",
        fake_ensure,
    )
    monkeypatch.setattr("hermes_cli.mcp_config._get_mcp_servers", lambda: {"jira": {"command": "uvx"}})
    monkeypatch.setattr(
        "tools.mcp_tool.list_connected_mcp_raw_tool_names",
        lambda _name: ["jira_search"],
    )
    monkeypatch.setattr(
        "hermes_cli.jira_dashboard._fetch_projects",
        lambda *_args, **_kwargs: [{"key": "BN", "name": "BN"}],
    )
    monkeypatch.setattr(
        "hermes_cli.jira_dashboard._resolve_project_key",
        lambda _projects, key: key,
    )
    monkeypatch.setattr(
        "hermes_cli.jira_dashboard._ensure_cloud_id",
        lambda *_args, **_kwargs: "cloud-1",
    )
    monkeypatch.setattr(
        "hermes_cli.jira_dashboard._issue_jql_variants",
        lambda project: [f'project = "{project}"'],
    )
    monkeypatch.setattr(
        "delivery_runtime.readiness.ticket_scope.load_ticket_scope_for_project",
        lambda _project: TicketScopeConfig(status_groups=("todo",)),
    )
    captured: dict = {}

    def fake_search(*_args, **kwargs):
        captured["jql_variants"] = kwargs.get("jql_variants")
        return [{"key": "BN-1", "fields": {"summary": "Test"}}]

    monkeypatch.setattr(
        "hermes_cli.jira_dashboard._search_issues_with_fallbacks",
        fake_search,
    )
    monkeypatch.setattr(
        "hermes_cli.jira_dashboard._normalize_issue",
        lambda raw: {"key": raw["key"], "summary": "Test"},
    )
    monkeypatch.setattr(
        "lc_server.integrations.jira_readiness.enrich_issue_snapshot",
        lambda raw, normalized, project_key: {**normalized, "projectKey": project_key},
    )

    from lc_server.integrations.jira_readiness import fetch_issues_for_readiness

    issues = fetch_issues_for_readiness("BN")
    assert ensure_calls == ["ensure"]
    assert issues == [{"key": "BN-1", "summary": "Test", "projectKey": "BN"}]
    assert captured["jql_variants"][0].startswith('project = "BN"')
    assert "statusCategory" in captured["jql_variants"][0]


def test_fetch_issues_for_readiness_surfaces_reconnect_errors(monkeypatch):
    from hermes_cli.jira_dashboard import JiraDashboardError

    monkeypatch.setattr(
        "hermes_cli.jira_dashboard.ensure_jira_mcp_connected",
        lambda: (_ for _ in ()).throw(JiraDashboardError("Could not connect to Jira.")),
    )

    from lc_server.integrations.jira_readiness import fetch_issues_for_readiness

    with pytest.raises(ReadinessIntegrationError, match="Could not connect to Jira"):
        fetch_issues_for_readiness("BN")


def test_extract_issue_comments_normalizes_adf_and_plain_text():
    from lc_server.integrations.jira_readiness import extract_issue_comments

    raw = {
        "fields": {
            "comment": {
                "comments": [
                    {
                        "author": {"displayName": "Alice"},
                        "created": "2026-06-11T10:00:00.000+0000",
                        "body": "Plain comment body",
                    },
                    {
                        "author": {"displayName": "Bob"},
                        "created": "2026-06-11T11:00:00.000+0000",
                        "body": {
                            "type": "doc",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Ticket reopened after QA."}],
                                }
                            ],
                        },
                    },
                ]
            }
        }
    }

    comments = extract_issue_comments(raw)

    assert len(comments) == 2
    assert comments[0]["author"] == "Alice"
    assert comments[0]["body"] == "Plain comment body"
    assert comments[1]["body"] == "Ticket reopened after QA."


def test_fetch_issue_snapshot_for_readiness_requests_comments(monkeypatch):
    ensure_calls: list[str] = []

    monkeypatch.setattr(
        "hermes_cli.jira_dashboard.ensure_jira_mcp_connected",
        lambda: ensure_calls.append("ensure"),
    )
    monkeypatch.setattr("hermes_cli.mcp_config._get_mcp_servers", lambda: {"jira": {"command": "uvx"}})
    monkeypatch.setattr(
        "tools.mcp_tool.list_connected_mcp_raw_tool_names",
        lambda _name: ["jira_get_issue"],
    )
    captured: dict[str, object] = {}

    def fake_invoke(_server, tool_name, arguments):
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        return {
            "result": {
                "key": "TVP-5",
                "fields": {
                    "summary": "Bug",
                    "description": "Details",
                    "status": {"name": "Reopened"},
                    "comment": {
                        "comments": [
                            {
                                "author": {"displayName": "QA"},
                                "created": "2026-06-11T09:00:00.000+0000",
                                "body": "Still failing in staging.",
                            }
                        ]
                    },
                },
            }
        }

    monkeypatch.setattr("tools.mcp_tool.invoke_mcp_tool", fake_invoke)
    monkeypatch.setattr(
        "hermes_cli.jira_dashboard._find_issue_detail_tool",
        lambda tool_names: tool_names[0] if tool_names else None,
    )
    monkeypatch.setattr(
        "hermes_cli.jira_dashboard._issue_detail_arg_variants",
        lambda _tool, issue_key, **kwargs: [
            {"issue_key": issue_key, "comment_limit": kwargs.get("comment_limit", 50)}
        ],
    )
    monkeypatch.setattr(
        "hermes_cli.jira_dashboard._parse_tool_payload",
        lambda parsed: parsed.get("result", parsed),
    )
    monkeypatch.setattr(
        "hermes_cli.jira_dashboard._extract_single_issue",
        lambda payload: payload if isinstance(payload, dict) and payload.get("key") else None,
    )
    monkeypatch.setattr(
        "hermes_cli.jira_dashboard._normalize_issue",
        lambda raw: {"key": raw["key"], "summary": "Bug", "description": "Details", "status": "Reopened"},
    )

    from lc_server.integrations.jira_readiness import fetch_issue_snapshot_for_readiness

    snapshot = fetch_issue_snapshot_for_readiness("TVP-5")

    assert ensure_calls == ["ensure"]
    assert captured["tool_name"] == "jira_get_issue"
    assert captured["arguments"]["comment_limit"] == 50
    assert snapshot["key"] == "TVP-5"
    assert snapshot["projectKey"] == "TVP"
    assert snapshot["comments"][0]["body"] == "Still failing in staging."
    assert snapshot["isReopened"] is True
