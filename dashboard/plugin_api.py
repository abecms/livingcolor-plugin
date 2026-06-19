"""LivingColor dashboard plugin backend.

Mounted at /api/plugins/livingcolor/ by the Hermes web server. This module
plays the role agent-lc's web_server.py wiring played: it bootstraps the
delivery server (DB init, service wiring, manifest auto-upgrade, scheduler)
in the dashboard process, which is the orchestration host.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

logger = logging.getLogger(__name__)

try:
    from jira_dashboard.compat import install_hermes_cli_jira_dashboard_shim
    from jira_dashboard.mcp_compat import install_mcp_tool_shims

    install_hermes_cli_jira_dashboard_shim()
    install_mcp_tool_shims()

    from lc_server.integrations.livingcolor_pm_profile import ensure_livingcolor_pm_profile
    from lc_server.integrations.project_chat_context import install_project_chat_context_hooks

    ensure_livingcolor_pm_profile()
    install_project_chat_context_hooks()
    logger.info("LivingColor project chat hooks installed from dashboard plugin_api")
except Exception:
    logger.exception("LivingColor project chat bootstrap failed during dashboard import")

from fastapi import APIRouter

from delivery_runtime.api.routes import router as delivery_router
from jira_dashboard.routes import router as jira_router
from lc_server.api.cloud_proxy import router as cloud_proxy_router
from lc_server.api.firebase_routes import router as firebase_router
from lc_server.api.mcp_routes import router as mcp_router
from lc_server.api.plugin_settings_routes import legacy_router as plugin_settings_legacy_router

router = APIRouter()
router.include_router(plugin_settings_legacy_router)
router.include_router(delivery_router, prefix="/delivery")
router.include_router(jira_router, prefix="/jira")
router.include_router(firebase_router, prefix="/firebase")
router.include_router(cloud_proxy_router, prefix="/cloud")
router.include_router(mcp_router, prefix="/mcp")

try:
    from lc_server.bootstrap import bootstrap_livingcolor_server

    bootstrap_livingcolor_server()
    logger.info("LivingColor delivery server bootstrapped (orchestration host)")
except Exception:
    # Routes still mount; endpoints return their structured "not ready"
    # errors until prerequisites are fixed. Never crash the host web server.
    logger.exception("LivingColor server bootstrap failed")
