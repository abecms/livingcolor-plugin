"""LivingColor Hermes plugin — agent-side surfaces.

Registers the /delivery slash command and the livingcolor model toolset.
The dashboard tab and HTTP API live under dashboard/ (loaded separately
by the Hermes web server's dashboard-plugin system).
"""
from __future__ import annotations

import sys
from pathlib import Path

# The ported packages (delivery_runtime, lc_server, jira_dashboard,
# lc_constants) use absolute imports; make them importable.
_PLUGIN_ROOT = Path(__file__).resolve().parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def register(ctx) -> None:
    """Hermes plugin entry point. Surfaces are added in later tasks."""
