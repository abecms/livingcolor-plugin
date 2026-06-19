"""Bridge profile-scoped Hermes homes to root MCP integration config.

Project dashboard chat runs the TUI under ``profiles/livingcolor-pm`` while
integrations are usually configured on the default ``~/.hermes`` home. Without
this bridge, PM tools see zero MCP servers even though the dashboard shows Jira
as configured.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def default_hermes_root() -> Path:
    try:
        from hermes_constants import get_default_hermes_root

        return Path(get_default_hermes_root())
    except Exception:
        return Path.home() / ".hermes"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml

        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        logger.debug("Could not read Hermes config at %s", path, exc_info=True)
        return {}


def load_root_mcp_servers() -> dict[str, dict[str, Any]]:
    """Return ``mcp_servers`` from the default Hermes home (not the active profile)."""
    root_mcp = _load_yaml(default_hermes_root() / "config.yaml").get("mcp_servers")
    if not isinstance(root_mcp, dict):
        return {}
    return {
        str(name): dict(config)
        for name, config in root_mcp.items()
        if str(name).strip() and isinstance(config, dict)
    }


def load_effective_mcp_servers() -> dict[str, dict[str, Any]]:
    """Active profile MCP servers merged with the default Hermes home."""
    try:
        from hermes_cli.mcp_config import _get_mcp_servers

        profile_servers = _get_mcp_servers()
    except ImportError:
        profile_servers = {}

    root_servers = load_root_mcp_servers()
    if not root_servers:
        return dict(profile_servers)

    merged = dict(root_servers)
    merged.update(profile_servers)
    return merged


def get_mcp_server_config(server_name: str) -> dict[str, Any] | None:
    cfg = load_effective_mcp_servers().get(server_name)
    if isinstance(cfg, dict) and cfg:
        return dict(cfg)
    return None
