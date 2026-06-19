"""Connect and status helpers for LivingColor integration MCP servers."""

from __future__ import annotations

from typing import Any

from lc_server.integrations.mcp_server_resolver import (
    active_github_mcp_name,
    active_gitlab_mcp_name,
    active_jira_mcp_name,
    resolve_github_mcp_server_name,
    resolve_gitlab_mcp_server_name,
    resolve_jira_mcp_server_name,
)

_CANONICAL_RESOLVERS = {
    "jira": resolve_jira_mcp_server_name,
    "gitlab": resolve_gitlab_mcp_server_name,
    "github": resolve_github_mcp_server_name,
}


def resolve_integration_server_name(name: str, servers: dict[str, Any] | None = None) -> str | None:
    """Resolve a requested MCP server name to a configured entry."""
    safe_name = (name or "").strip()
    if not safe_name:
        return None

    if servers is None:
        from lc_server.integrations.mcp_config_bridge import load_effective_mcp_servers

        servers = load_effective_mcp_servers()

    if safe_name in servers:
        return safe_name

    resolver = _CANONICAL_RESOLVERS.get(safe_name.lower())
    if resolver is None:
        return None

    return resolver(servers)


def resolve_integration_server_entry(
    name: str,
    servers: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]] | None:
    resolved = resolve_integration_server_name(name, servers)
    if not resolved:
        return None
    if servers is None:
        from lc_server.integrations.mcp_config_bridge import load_effective_mcp_servers

        servers = load_effective_mcp_servers()
    cfg = servers.get(resolved)
    if not isinstance(cfg, dict) or not cfg:
        return None
    return resolved, dict(cfg)


def preferred_integration_server_name(kind: str, servers: dict[str, Any] | None = None) -> str:
    kind = (kind or "").strip().lower()
    if servers is None:
        from lc_server.integrations.mcp_config_bridge import load_effective_mcp_servers

        servers = load_effective_mcp_servers()

    if kind == "jira":
        return active_jira_mcp_name(servers)
    if kind == "gitlab":
        return active_gitlab_mcp_name(servers)
    if kind == "github":
        return active_github_mcp_name(servers)
    return kind


def _read_env(cfg: dict[str, Any]) -> dict[str, str]:
    env = cfg.get("env")
    if not isinstance(env, dict):
        return {}
    return {str(key): str(value) for key, value in env.items() if value is not None and str(value).strip()}


def _read_gitlab_url(cfg: dict[str, Any]) -> str | None:
    api_url = _read_env(cfg).get("GITLAB_API_URL", "").strip()
    if not api_url:
        return None
    return api_url.replace("/api/v4/", "").replace("/api/v4", "").rstrip("/") or None


def _read_jira_url(cfg: dict[str, Any]) -> str | None:
    return _read_env(cfg).get("JIRA_URL") or None


def _server_connected(name: str) -> bool:
    from tools.mcp_tool import get_mcp_status

    for entry in get_mcp_status():
        if entry.get("name") == name and entry.get("connected"):
            return True
    return False


def connect_mcp_server(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    from tools.mcp_tool import list_connected_mcp_tool_names, reconnect_mcp_server

    reconnect_mcp_server(name, cfg)
    connected = _server_connected(name)
    tool_count = len(list_connected_mcp_tool_names(name)) if connected else 0
    status = "connected" if connected else "disconnected"
    message = "Connected via MCP." if connected else f"Could not connect to MCP server '{name}'."
    payload: dict[str, Any] = {
        "ok": connected,
        "status": status,
        "message": message,
        "authenticated": connected,
        "toolCount": tool_count,
        "serverName": name,
    }
    gitlab_url = _read_gitlab_url(cfg)
    if gitlab_url:
        payload["gitlabUrl"] = gitlab_url
    jira_url = _read_jira_url(cfg)
    if jira_url:
        payload["jiraUrl"] = jira_url
    return payload


def status_mcp_server(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    from tools.mcp_tool import list_connected_mcp_tool_names

    connected = _server_connected(name)
    tool_count = len(list_connected_mcp_tool_names(name)) if connected else 0
    payload: dict[str, Any] = {
        "ok": connected,
        "status": "connected" if connected else "disconnected",
        "message": "Connected via MCP." if connected else "Configured, but not connected in the backend session.",
        "authenticated": connected,
        "toolCount": tool_count,
        "serverName": name,
    }
    gitlab_url = _read_gitlab_url(cfg)
    if gitlab_url:
        payload["gitlabUrl"] = gitlab_url
    jira_url = _read_jira_url(cfg)
    if jira_url:
        payload["jiraUrl"] = jira_url
    return payload


def connect_gitlab_mcp() -> dict[str, Any]:
    from lc_server.integrations.mcp_config_bridge import load_effective_mcp_servers

    servers = load_effective_mcp_servers()
    entry = resolve_integration_server_entry("gitlab", servers)
    if not entry:
        return {
            "ok": False,
            "status": "disconnected",
            "message": "GitLab MCP is not configured yet.",
            "authenticated": False,
            "toolCount": 0,
        }
    name, cfg = entry
    return connect_mcp_server(name, cfg)


def connect_github_mcp() -> dict[str, Any]:
    from lc_server.integrations.mcp_config_bridge import load_effective_mcp_servers

    servers = load_effective_mcp_servers()
    entry = resolve_integration_server_entry("github", servers)
    if not entry:
        return {
            "ok": False,
            "status": "disconnected",
            "message": "GitHub MCP is not configured yet.",
            "authenticated": False,
            "toolCount": 0,
        }
    name, cfg = entry
    return connect_mcp_server(name, cfg)


def integration_status(kind: str) -> dict[str, Any]:
    from lc_server.integrations.mcp_config_bridge import load_effective_mcp_servers

    servers = load_effective_mcp_servers()
    entry = resolve_integration_server_entry(kind, servers)
    if not entry:
        label = kind.capitalize()
        return {
            "ok": False,
            "status": "disconnected",
            "message": f"{label} MCP is not configured yet.",
            "authenticated": False,
            "toolCount": 0,
            "configured": False,
            "serverName": None,
        }
    name, cfg = entry
    payload = status_mcp_server(name, cfg)
    payload["configured"] = True
    return payload


def upsert_integration_server_config(name: str, body: dict[str, Any]) -> dict[str, Any]:
    safe_name = (name or "").strip()
    if not safe_name:
        raise ValueError("Server name is required")
    if not body.get("url") and not body.get("command"):
        raise ValueError("Provide either a URL (HTTP/SSE server) or a command (stdio server)")

    from hermes_cli.mcp_config import _save_mcp_server
    from lc_server.integrations.mcp_config_bridge import load_effective_mcp_servers

    servers = load_effective_mcp_servers()
    target_name = resolve_integration_server_name(safe_name, servers) or safe_name
    existing = servers.get(target_name) or {}
    merged = {**existing, **body}
    if isinstance(body.get("env"), dict):
        merged["env"] = dict(body["env"])

    if not _save_mcp_server(target_name, merged):
        raise ValueError("Server rejected: suspicious command/args configuration")

    return {"ok": True, "name": target_name}
