"""Provision Hermes MCP server entries from process environment variables.

Used by cloud bootstrap and server startup so ``setup-automation`` can succeed on
fresh runners when Cursor Cloud injects secrets into ``os.environ``. Never logs
or returns secret values — safe for public-repo code (secrets stay in env only).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CREDENTIAL_ENV_NAMES = (
    "JIRA_URL",
    "JIRA_USERNAME",
    "JIRA_API_TOKEN",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "STRIPE_SECRET_KEY",
    "OPENROUTER_API_KEY",
)

_JIRA_MCP_TEMPLATE: dict[str, Any] = {
    "command": "uvx",
    "args": ["mcp-atlassian"],
}

_GITHUB_MCP_TEMPLATE: dict[str, Any] = {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
}


def _strip_env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _github_token_from_env() -> str:
    return _strip_env("GITHUB_TOKEN") or _strip_env("GH_TOKEN")


def _jira_mcp_config_from_env() -> dict[str, Any] | None:
    jira_url = _strip_env("JIRA_URL")
    jira_token = _strip_env("JIRA_API_TOKEN")
    if not jira_url or not jira_token:
        return None
    env = {
        "JIRA_URL": jira_url,
        "JIRA_API_TOKEN": jira_token,
    }
    jira_user = _strip_env("JIRA_USERNAME")
    if jira_user:
        env["JIRA_USERNAME"] = jira_user
    return {**_JIRA_MCP_TEMPLATE, "env": env}


def _github_mcp_config_from_env() -> dict[str, Any] | None:
    token = _github_token_from_env()
    if not token:
        return None
    return {
        **_GITHUB_MCP_TEMPLATE,
        "env": {
            "GITHUB_PERSONAL_ACCESS_TOKEN": token,
            "GITHUB_TOKEN": token,
        },
    }


def _save_via_hermes(name: str, config: dict[str, Any]) -> bool:
    try:
        from hermes_cli.mcp_config import _save_mcp_server

        return bool(_save_mcp_server(name, config))
    except ImportError:
        return False


def _write_root_config_yaml(servers: dict[str, dict[str, Any]]) -> None:
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML unavailable; cannot write Hermes MCP config from environment")
        return

    from lc_server.integrations.mcp_config_bridge import default_hermes_root

    cfg_path = default_hermes_root() / "config.yaml"
    data: dict[str, Any] = {}
    if cfg_path.is_file():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded

    existing = data.get("mcp_servers")
    if not isinstance(existing, dict):
        existing = {}
    existing.update(servers)
    data["mcp_servers"] = existing
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def ensure_mcp_servers_from_env() -> list[str]:
    """Write Jira/GitHub MCP entries when matching env vars are present.

    Returns canonical server names that were provisioned (``jira``, ``github``).
    Idempotent: re-running refreshes env blocks from the current process environment.
    """
    provisioned: list[str] = []
    pending: dict[str, dict[str, Any]] = {}

    jira_cfg = _jira_mcp_config_from_env()
    if jira_cfg is not None:
        if _save_via_hermes("jira", jira_cfg):
            provisioned.append("jira")
        else:
            pending["jira"] = jira_cfg

    github_cfg = _github_mcp_config_from_env()
    if github_cfg is not None:
        if _save_via_hermes("github", github_cfg):
            provisioned.append("github")
        else:
            pending["github"] = github_cfg

    if pending:
        _write_root_config_yaml(pending)
        provisioned.extend(sorted(pending))

    if provisioned:
        logger.info("Provisioned MCP servers from environment: %s", ", ".join(provisioned))
    else:
        logger.debug("No Jira/GitHub credentials in environment; MCP bootstrap skipped")

    return provisioned


def credential_env_status() -> dict[str, str]:
    """Return configured/missing status for known credential env vars (no values)."""
    status: dict[str, str] = {}
    for name in _CREDENTIAL_ENV_NAMES:
        status[name] = "configured" if _strip_env(name) else "missing"
    if status.get("GITHUB_TOKEN") == "missing" and status.get("GH_TOKEN") == "configured":
        status["GITHUB_TOKEN"] = "configured"
    return status


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[mcp-env-bootstrap] %(message)s")
    ensure_mcp_servers_from_env()
    for name, value in credential_env_status().items():
        print(f"{name}={value}")


if __name__ == "__main__":
    main()
