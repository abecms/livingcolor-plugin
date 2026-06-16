"""Tests for Hermes MCP server name resolution."""

from __future__ import annotations

from lc_server.integrations.mcp_server_resolver import (
    active_gitlab_mcp_name,
    active_jira_mcp_name,
    resolve_gitlab_mcp_server_name,
    resolve_jira_mcp_server_name,
)


def test_resolve_jira_from_atlassian_named_server():
    servers = {
        "Atlassian": {
            "command": "uvx",
            "args": ["mcp-atlassian"],
            "env": {
                "JIRA_URL": "https://example.atlassian.net/",
                "JIRA_USERNAME": "user@example.com",
                "JIRA_API_TOKEN": "secret",
            },
        }
    }

    assert resolve_jira_mcp_server_name(servers) == "Atlassian"
    assert active_jira_mcp_name(servers) == "Atlassian"


def test_resolve_gitlab_from_custom_named_server():
    servers = {
        "gitlab-tv5": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-gitlab"],
            "env": {
                "GITLAB_API_URL": "https://gitlab.com/api/v4/",
                "GITLAB_PERSONAL_ACCESS_TOKEN": "secret",
            },
        }
    }

    assert resolve_gitlab_mcp_server_name(servers) == "gitlab-tv5"
    assert active_gitlab_mcp_name(servers) == "gitlab-tv5"


def test_prefers_canonical_jira_when_present():
    servers = {
        "jira": {"command": "uvx", "args": ["mcp-atlassian"], "env": {"JIRA_URL": "https://a/"}},
        "Atlassian": {"command": "uvx", "args": ["mcp-atlassian"], "env": {"JIRA_URL": "https://b/"}},
    }

    assert resolve_jira_mcp_server_name(servers) == "jira"
