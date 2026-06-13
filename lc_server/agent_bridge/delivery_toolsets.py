"""Resolve Hermes toolsets for LivingColor delivery agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from delivery_runtime.readiness.project_settings import load_project_vcs_provider

if TYPE_CHECKING:
    from delivery_runtime.agents.schema import AgentManifest


def _mcp_toolset_name(server_name: str) -> str:
    return f"mcp-{server_name}"


def _configured_mcp_server_names() -> list[str]:
    try:
        from hermes_cli.mcp_config import _get_mcp_servers
    except ImportError:
        return []

    servers = _get_mcp_servers()
    if not isinstance(servers, dict):
        return []
    return [str(name).strip() for name in servers if str(name).strip()]


def _project_mcp_server_names(project_key: str | None) -> list[str]:
    key = (project_key or "").strip().upper()
    if not key:
        return []
    from delivery_runtime.readiness.project_settings import load_project_mcp_servers

    stored = load_project_mcp_servers(key)
    if not isinstance(stored, dict):
        return []
    return [str(name).strip() for name in stored if str(name).strip()]


def _append_mcp_toolsets(toolsets: list[str], server_names: list[str]) -> list[str]:
    out = list(toolsets)
    seen = set(out)
    for server_name in server_names:
        mcp_toolset = _mcp_toolset_name(server_name)
        if mcp_toolset not in seen:
            out.append(mcp_toolset)
            seen.add(mcp_toolset)
    return out


def resolve_delivery_toolsets(
    *,
    base_toolsets: list[str],
    manifest: AgentManifest | None,
    project_key: str | None,
) -> list[str]:
    """Append project MCP toolsets when the manifest inherits project MCP config."""
    toolsets = [str(item).strip() for item in base_toolsets if str(item).strip()]

    inherit = "project"
    if manifest is not None:
        inherit = str(manifest.mcp.inherit or "").strip().lower() or "project"

    if inherit != "project":
        return toolsets

    server_names = list(dict.fromkeys(_project_mcp_server_names(project_key) + _configured_mcp_server_names()))
    return _append_mcp_toolsets(toolsets, server_names)


def _vcs_mcp_server_names(project_key: str | None) -> list[str]:
    provider = load_project_vcs_provider(project_key or "") if project_key else "gitlab"
    names: list[str] = []
    for server_name in dict.fromkeys(_project_mcp_server_names(project_key) + _configured_mcp_server_names()):
        if provider in server_name.lower():
            names.append(server_name)
    return names or [provider]


def resolve_publisher_toolsets(
    *,
    base_toolsets: list[str],
    manifest: AgentManifest | None,
    project_key: str | None,
) -> list[str]:
    """Publisher must load VCS MCP toolsets so review-request creation never falls back to curl."""
    toolsets = resolve_delivery_toolsets(
        base_toolsets=base_toolsets,
        manifest=manifest,
        project_key=project_key,
    )
    return _append_mcp_toolsets(toolsets, _vcs_mcp_server_names(project_key))
