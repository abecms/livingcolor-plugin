"""Restore saved MCP sessions when the LivingColor backend starts."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_WARMUP_SERVERS = ("jira", "gitlab")


def warm_configured_mcp_connections() -> None:
    """Reconnect jira/gitlab MCP servers that are already configured on disk."""
    try:
        from hermes_cli.mcp_config import _get_mcp_servers
        from hermes_cli.mcp_runtime import connect_mcp_server
    except ImportError:
        return

    servers = _get_mcp_servers()
    for name in _WARMUP_SERVERS:
        if name not in servers:
            continue
        try:
            result = connect_mcp_server(name)
            if result.get("ok"):
                logger.info("Restored MCP session for %s on backend startup", name)
            else:
                logger.debug(
                    "MCP warm connect for %s did not succeed: %s",
                    name,
                    result.get("message") or "unknown error",
                )
        except Exception as exc:
            logger.warning("MCP warm connect for %s failed: %s", name, exc)
