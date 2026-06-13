"""Compatibility shims for upstream Hermes ``tools.mcp_tool``.

The plugin was ported from the agent-lc fork, where ``tools/mcp_tool.py``
exposes synchronous helpers used by the delivery backend:

- ``invoke_mcp_tool``
- ``list_connected_mcp_tool_names`` / ``list_connected_mcp_raw_tool_names``
- ``shutdown_mcp_server`` / ``reconnect_mcp_server``

Upstream Hermes only exposes the registry-level API (``register_mcp_servers``,
``_make_tool_handler``, ...). Install fork-equivalent helpers on the
``tools.mcp_tool`` module at plugin startup so every existing
``from tools.mcp_tool import invoke_mcp_tool`` call site works unchanged.

On the agent-lc fork the symbols already exist and nothing is patched.
"""
from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

_SHIM_SYMBOLS = (
    "invoke_mcp_tool",
    "list_connected_mcp_tool_names",
    "list_connected_mcp_raw_tool_names",
    "shutdown_mcp_server",
    "reconnect_mcp_server",
)

_installed = False


def install_mcp_tool_shims() -> None:
    """Add missing fork helpers to ``tools.mcp_tool`` (idempotent)."""
    global _installed
    if _installed:
        return

    import tools.mcp_tool as mcp

    missing = [name for name in _SHIM_SYMBOLS if not hasattr(mcp, name)]
    if not missing:
        _installed = True
        return

    def list_connected_mcp_tool_names(server_name: str) -> List[str]:
        """Return Hermes registry tool names registered on a connected server."""
        with mcp._lock:
            server = mcp._servers.get(server_name)
            if not server or not server.session:
                return []
            if hasattr(server, "_registered_tool_names"):
                return list(server._registered_tool_names)
            return [t.name for t in getattr(server, "_tools", [])]

    def list_connected_mcp_raw_tool_names(server_name: str) -> List[str]:
        """Return MCP wire tool names (without the ``mcp_{server}_`` prefix)."""
        with mcp._lock:
            server = mcp._servers.get(server_name)
            if not server or not server.session:
                return []
            return [t.name for t in getattr(server, "_tools", [])]

    def _resolve_mcp_wire_tool_name(server_name: str, tool_name: str) -> str:
        """Map a Hermes registry tool name back to the MCP protocol tool name."""
        with mcp._lock:
            server = mcp._servers.get(server_name)
        if not server:
            return tool_name

        tools = getattr(server, "_tools", []) or []
        if any(getattr(tool, "name", None) == tool_name for tool in tools):
            return tool_name

        safe_server = mcp.sanitize_mcp_name_component(server_name)
        prefix = f"mcp_{safe_server}_"
        if tool_name.startswith(prefix):
            sanitized_suffix = tool_name[len(prefix):]
            for tool in tools:
                if mcp.sanitize_mcp_name_component(getattr(tool, "name", "")) == sanitized_suffix:
                    return tool.name

        return tool_name

    def invoke_mcp_tool(
        server_name: str,
        tool_name: str,
        arguments: Optional[dict] = None,
        *,
        timeout: Optional[float] = None,
    ) -> dict:
        """Call a registered MCP tool synchronously and return a parsed JSON dict."""
        try:
            from delivery_runtime.shadow.guards import check_mcp_tool, mcp_block_response

            violation = check_mcp_tool(server_name, tool_name)
            if violation is not None:
                return mcp_block_response(violation)
        except Exception:
            pass
        args = arguments or {}
        wire_tool_name = _resolve_mcp_wire_tool_name(server_name, tool_name)
        with mcp._lock:
            server = mcp._servers.get(server_name)
        tool_timeout = timeout
        if tool_timeout is None:
            tool_timeout = (
                getattr(server, "tool_timeout", mcp._DEFAULT_TOOL_TIMEOUT)
                if server
                else mcp._DEFAULT_TOOL_TIMEOUT
            )
        handler = mcp._make_tool_handler(server_name, wire_tool_name, tool_timeout)
        raw = handler(args)
        try:
            parsed: Any = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {"result": raw}
        if not isinstance(parsed, dict):
            return {"result": parsed}
        return parsed

    def shutdown_mcp_server(server_name: str) -> None:
        """Shut down one MCP server and remove it from the active pool."""
        with mcp._lock:
            server = mcp._servers.pop(server_name, None)
            loop = mcp._mcp_loop

        # Upstream tracks the circuit breaker via _reset_server_error.
        reset = getattr(mcp, "_reset_server_error", None)
        if callable(reset):
            try:
                reset(server_name)
            except Exception:
                pass

        if not server:
            return

        async def _do_shutdown() -> None:
            try:
                await server.shutdown()
            except BaseException as exc:
                logger.debug("Error shutting down MCP server '%s': %s", server_name, exc)

        if loop is not None and loop.is_running():
            import asyncio

            try:
                future = asyncio.run_coroutine_threadsafe(_do_shutdown(), loop)
                future.result(timeout=15)
            except BaseException as exc:
                logger.debug("Error during MCP shutdown for '%s': %s", server_name, exc)

    def reconnect_mcp_server(server_name: str, config: dict) -> List[str]:
        """Restart one MCP server from fresh config."""
        shutdown_mcp_server(server_name)
        return mcp.register_mcp_servers({server_name: config})

    shims = {
        "list_connected_mcp_tool_names": list_connected_mcp_tool_names,
        "list_connected_mcp_raw_tool_names": list_connected_mcp_raw_tool_names,
        "invoke_mcp_tool": invoke_mcp_tool,
        "shutdown_mcp_server": shutdown_mcp_server,
        "reconnect_mcp_server": reconnect_mcp_server,
    }
    for name in missing:
        setattr(mcp, name, shims[name])
    logger.info("Installed tools.mcp_tool compat shims: %s", ", ".join(missing))
    _installed = True
