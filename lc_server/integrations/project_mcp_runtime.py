"""Apply per-project MCP server configs from project_mapping.yaml."""

from __future__ import annotations

import logging
from typing import Any

from delivery_runtime.readiness.project_settings import (
    load_project_mcp_servers,
    persist_project_mcp_server,
)

logger = logging.getLogger(__name__)

_PROJECT_SCOPED_SERVERS = frozenset({"jira", "gitlab"})


def apply_project_mcp_runtime(project_key: str | None) -> None:
    """Swap active jira/gitlab MCP entries to the requested project's saved config."""
    key = (project_key or "").strip().upper()
    if not key:
        return

    try:
        from hermes_cli.mcp_config import _get_mcp_servers, _remove_mcp_server, _save_mcp_server
    except ImportError:
        return

    stored = load_project_mcp_servers(key)
    current = _get_mcp_servers()

    for server_name in _PROJECT_SCOPED_SERVERS:
        project_cfg = stored.get(server_name)
        if isinstance(project_cfg, dict) and project_cfg:
            merged = {**(current.get(server_name) or {}), **project_cfg}
            _save_mcp_server(server_name, merged)
            continue
        if server_name in current:
            _remove_mcp_server(server_name)


def persist_project_mcp_runtime(project_key: str | None, server_name: str, server_config: dict[str, Any]) -> None:
    key = (project_key or "").strip().upper()
    name = (server_name or "").strip()
    if not key or not name:
        return
    if name not in _PROJECT_SCOPED_SERVERS:
        return

    persist_project_mcp_server(key, name, server_config)


def install_project_mcp_hooks() -> None:
    """Persist jira/gitlab MCP saves under the active project when a project header is set."""
    try:
        import hermes_cli.mcp_config as mcp_config
    except ImportError:
        return

    if getattr(mcp_config, "_livingcolor_project_mcp_hook_installed", False):
        return

    original_save = mcp_config._save_mcp_server

    def _save_with_project_scope(name: str, server_config: dict[str, Any]) -> None:
        from lc_server.context import get_project_context

        ctx = get_project_context()
        project_key = ctx.normalized_project_key() if ctx is not None else ""
        if project_key and name in _PROJECT_SCOPED_SERVERS:
            persist_project_mcp_server(project_key, name, server_config)
        original_save(name, server_config)

    mcp_config._save_mcp_server = _save_with_project_scope
    mcp_config._livingcolor_project_mcp_hook_installed = True
    logger.debug("Installed LivingColor per-project MCP save hook")
