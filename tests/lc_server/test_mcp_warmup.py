"""Tests for MCP warm connect on LivingColor server bootstrap."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_warm_configured_mcp_connections_reconnects_saved_servers():
    from lc_server.integrations.mcp_warmup import warm_configured_mcp_connections

    connect = MagicMock(side_effect=[{"ok": True}, {"ok": False, "message": "offline"}])
    servers = {
        "Atlassian": {"command": "uvx", "args": ["mcp-atlassian"], "env": {"JIRA_URL": "https://a/"}},
        "gitlab-tv5": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-gitlab"],
            "env": {"GITLAB_API_URL": "https://gitlab.com/api/v4/"},
        },
    }
    with patch("hermes_cli.mcp_config._get_mcp_servers", return_value=servers), patch(
        "hermes_cli.mcp_runtime.connect_mcp_server", connect
    ):
        warm_configured_mcp_connections()

    assert connect.call_count == 2
    connect.assert_any_call("Atlassian")
    connect.assert_any_call("gitlab-tv5")


def test_warm_configured_mcp_connections_skips_unconfigured_servers():
    from lc_server.integrations.mcp_warmup import warm_configured_mcp_connections

    connect = MagicMock()
    with patch("hermes_cli.mcp_config._get_mcp_servers", return_value={"other": {}}), patch(
        "hermes_cli.mcp_runtime.connect_mcp_server", connect
    ):
        warm_configured_mcp_connections()

    connect.assert_not_called()
