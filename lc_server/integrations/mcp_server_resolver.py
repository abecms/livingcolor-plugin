"""Resolve Hermes MCP server names from user config (not only canonical jira/gitlab/github)."""

from __future__ import annotations

from typing import Any

CANONICAL_JIRA_MCP_NAME = "jira"
CANONICAL_GITLAB_MCP_NAME = "gitlab"
CANONICAL_GITHUB_MCP_NAME = "github"


def _args_blob(config: dict[str, Any]) -> str:
    args = config.get("args") or []
    if not isinstance(args, list):
        return ""
    return " ".join(str(item) for item in args).lower()


def _env_keys(config: dict[str, Any]) -> set[str]:
    env = config.get("env")
    if not isinstance(env, dict):
        return set()
    return {str(key).upper() for key in env.keys()}


def is_jira_mcp_server(name: str, config: dict[str, Any]) -> bool:
    lowered = (name or "").strip().lower()
    if lowered in {CANONICAL_JIRA_MCP_NAME, "atlassian"} or "jira" in lowered or "atlassian" in lowered:
        return True
    args = _args_blob(config)
    if "mcp-atlassian" in args:
        return True
    if "mcp-remote" in args and "atlassian" in args:
        return True
    env = _env_keys(config)
    return "JIRA_URL" in env or "JIRA_USERNAME" in env


def is_gitlab_mcp_server(name: str, config: dict[str, Any]) -> bool:
    lowered = (name or "").strip().lower()
    if lowered == CANONICAL_GITLAB_MCP_NAME or "gitlab" in lowered:
        return True
    args = _args_blob(config)
    if "server-gitlab" in args or "@modelcontextprotocol/server-gitlab" in args:
        return True
    return "GITLAB_API_URL" in _env_keys(config) or "GITLAB_PERSONAL_ACCESS_TOKEN" in _env_keys(config)


def is_github_mcp_server(name: str, config: dict[str, Any]) -> bool:
    lowered = (name or "").strip().lower()
    if lowered == CANONICAL_GITHUB_MCP_NAME or "github" in lowered:
        return True
    args = _args_blob(config)
    if "server-github" in args or "@modelcontextprotocol/server-github" in args:
        return True
    return "GITHUB_PERSONAL_ACCESS_TOKEN" in _env_keys(config)


def _resolve_server_name(
    *,
    canonical: str,
    predicate,
    servers: dict[str, Any],
) -> str | None:
    if not isinstance(servers, dict):
        return None
    canonical_cfg = servers.get(canonical)
    if isinstance(canonical_cfg, dict) and predicate(canonical, canonical_cfg):
        return canonical
    for name, config in servers.items():
        if not isinstance(config, dict):
            continue
        if predicate(str(name), config):
            return str(name)
    return None


def resolve_jira_mcp_server_name(servers: dict[str, Any] | None = None) -> str | None:
    if servers is None:
        from lc_server.integrations.mcp_config_bridge import load_effective_mcp_servers

        servers = load_effective_mcp_servers()
    return _resolve_server_name(canonical=CANONICAL_JIRA_MCP_NAME, predicate=is_jira_mcp_server, servers=servers)


def resolve_gitlab_mcp_server_name(servers: dict[str, Any] | None = None) -> str | None:
    if servers is None:
        from lc_server.integrations.mcp_config_bridge import load_effective_mcp_servers

        servers = load_effective_mcp_servers()
    return _resolve_server_name(canonical=CANONICAL_GITLAB_MCP_NAME, predicate=is_gitlab_mcp_server, servers=servers)


def resolve_github_mcp_server_name(servers: dict[str, Any] | None = None) -> str | None:
    if servers is None:
        from lc_server.integrations.mcp_config_bridge import load_effective_mcp_servers

        servers = load_effective_mcp_servers()
    return _resolve_server_name(canonical=CANONICAL_GITHUB_MCP_NAME, predicate=is_github_mcp_server, servers=servers)


def active_jira_mcp_name(servers: dict[str, Any] | None = None) -> str:
    return resolve_jira_mcp_server_name(servers) or CANONICAL_JIRA_MCP_NAME


def active_gitlab_mcp_name(servers: dict[str, Any] | None = None) -> str:
    return resolve_gitlab_mcp_server_name(servers) or CANONICAL_GITLAB_MCP_NAME


def active_github_mcp_name(servers: dict[str, Any] | None = None) -> str:
    return resolve_github_mcp_server_name(servers) or CANONICAL_GITHUB_MCP_NAME
