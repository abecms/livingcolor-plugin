"""Tests for MCP connect helpers."""

from __future__ import annotations

from lc_server.integrations.mcp_connect import (
    resolve_integration_server_entry,
    resolve_integration_server_name,
    upsert_integration_server_config,
)


def test_resolve_integration_server_name_finds_custom_jira_server():
    servers = {
        "Atlassian": {
            "command": "uvx",
            "args": ["mcp-atlassian"],
            "env": {"JIRA_URL": "https://example.atlassian.net/"},
        }
    }

    assert resolve_integration_server_name("jira", servers) == "Atlassian"
    assert resolve_integration_server_entry("jira", servers) == (
        "Atlassian",
        servers["Atlassian"],
    )


def test_upsert_integration_server_config_updates_existing_alias(monkeypatch):
    saved: dict[str, object] = {}
    servers = {
        "gitlab-tv5": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-gitlab"],
            "env": {"GITLAB_API_URL": "https://gitlab.com/api/v4/"},
        }
    }

    monkeypatch.setattr("hermes_cli.mcp_config._get_mcp_servers", lambda: servers)

    def fake_save(name: str, config: dict) -> bool:
        saved["name"] = name
        saved["config"] = config
        return True

    monkeypatch.setattr("hermes_cli.mcp_config._save_mcp_server", fake_save)

    result = upsert_integration_server_config(
        "gitlab",
        {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-gitlab"],
            "env": {
                "GITLAB_API_URL": "https://gitlab.tv5monde.com/api/v4/",
                "GITLAB_PERSONAL_ACCESS_TOKEN": "secret",
            },
        },
    )

    assert result == {"ok": True, "name": "gitlab-tv5"}
    assert saved["name"] == "gitlab-tv5"
