"""Tests for MCP warm connect on LivingColor server bootstrap."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_warm_configured_mcp_connections_reconnects_saved_servers():
    from lc_server.integrations.mcp_warmup import warm_configured_mcp_connections

    connect = MagicMock(side_effect=[{"ok": True}, {"ok": False, "message": "offline"}])
    with patch("hermes_cli.mcp_config._get_mcp_servers", return_value={"jira": {}, "gitlab": {}}), patch(
        "hermes_cli.mcp_runtime.connect_mcp_server", connect
    ):
        warm_configured_mcp_connections()

    assert connect.call_count == 2
    connect.assert_any_call("jira")
    connect.assert_any_call("gitlab")


def test_warm_configured_mcp_connections_skips_unconfigured_servers():
    from lc_server.integrations.mcp_warmup import warm_configured_mcp_connections

    connect = MagicMock()
    with patch("hermes_cli.mcp_config._get_mcp_servers", return_value={"jira": {}}), patch(
        "hermes_cli.mcp_runtime.connect_mcp_server", connect
    ):
        warm_configured_mcp_connections()

    connect.assert_called_once_with("jira")
