"""Bridge ported agent-lc imports to the plugin's jira_dashboard package.

agent-lc code imports ``hermes_cli.jira_dashboard`` (fork-only). Upstream
Hermes has no such module; the plugin owns the implementation in
``jira_dashboard.service``. Install this shim at process startup so lazy
imports in ``lc_server`` and ``delivery_runtime`` resolve correctly.
"""
from __future__ import annotations

import sys

_installed = False


def install_hermes_cli_jira_dashboard_shim() -> None:
    """Register ``jira_dashboard.service`` as ``hermes_cli.jira_dashboard``."""
    global _installed
    if _installed:
        return

    import hermes_cli
    from jira_dashboard import service

    sys.modules["hermes_cli.jira_dashboard"] = service
    hermes_cli.jira_dashboard = service  # type: ignore[attr-defined]
    _installed = True
