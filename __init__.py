"""LivingColor Hermes plugin — agent-side surfaces.

Registers the /delivery slash command and the livingcolor model toolset.
The dashboard tab and HTTP API live under dashboard/ (loaded separately
by the Hermes web server's dashboard-plugin system).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# The ported packages (delivery_runtime, lc_server, jira_dashboard,
# lc_constants) use absolute imports; make them importable.
_PLUGIN_ROOT = Path(__file__).resolve().parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def register(ctx) -> None:
    """Hermes plugin entry point."""
    from jira_dashboard.compat import install_hermes_cli_jira_dashboard_shim
    from jira_dashboard.mcp_compat import install_mcp_tool_shims

    install_hermes_cli_jira_dashboard_shim()
    install_mcp_tool_shims()

    from agent_surfaces import register_surfaces

    register_surfaces(ctx)

    try:
        from lc_server.integrations.livingcolor_pm_profile import ensure_livingcolor_pm_profile
        from lc_server.integrations.project_chat_context import install_project_chat_context_hooks

        ensure_livingcolor_pm_profile()
        install_project_chat_context_hooks()
    except Exception:
        logger.exception("LivingColor project chat bootstrap failed during plugin register")
