"""LivingColor Server bootstrap."""

from __future__ import annotations

import logging

from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.automation.scheduler import DailyAnalysisScheduler
from lc_server.factory import build_delivery_services

logger = logging.getLogger(__name__)

_scheduler: DailyAnalysisScheduler | None = None


def _run_scheduled_daily_analysis() -> None:
    from delivery_runtime.api import deps

    services = deps.get_services()
    config = load_delivery_automation_config()
    services.pm_inbox.run_daily_analysis(config.project_key)


def bootstrap_lc_server() -> None:
    """Wire delivery runtime API dependencies to server-owned services."""
    global _scheduler
    from lc_server.env_loader import load_livingcolor_dotenv

    load_livingcolor_dotenv(override=True)

    from delivery_runtime.api import deps
    from delivery_runtime.persistence.db import init_db
    from lc_server.bundled_credentials import ensure_bundled_openrouter_credentials
    from lc_server.model_defaults import ensure_livingcolor_fixed_model

    try:
        ensure_bundled_openrouter_credentials()
    except Exception as exc:
        logger.warning("Could not apply bundled OpenRouter credentials: %s", exc)

    try:
        ensure_livingcolor_fixed_model()
    except Exception as exc:
        logger.warning("Could not apply LivingColor fixed model defaults: %s", exc)

    try:
        init_db()
    except Exception as exc:
        logger.warning("Delivery persistence is not ready yet: %s", exc)

    try:
        from lc_server.provisioning.upgrade import upgrade_all_project_manifests

        upgrade_all_project_manifests()
    except Exception as exc:
        logger.warning("Agent manifest auto-upgrade skipped: %s", exc)

    deps.configure(build_delivery_services())

    try:
        from lc_server.integrations.project_mcp_runtime import install_project_mcp_hooks

        install_project_mcp_hooks()
    except Exception as exc:
        logger.warning("Could not install per-project MCP hooks: %s", exc)

    try:
        from lc_server.integrations.mcp_warmup import warm_configured_mcp_connections

        warm_configured_mcp_connections()
    except Exception as exc:
        logger.warning("MCP warm connect on startup skipped: %s", exc)

    config = load_delivery_automation_config()
    if config.daily_analysis_cron.enabled:
        _scheduler = DailyAnalysisScheduler(runner=_run_scheduled_daily_analysis)
        _scheduler.start()
        logger.info(
            "Daily analysis scheduler enabled for %s at %02d:%02d UTC",
            config.project_key,
            config.daily_analysis_cron.hour,
            config.daily_analysis_cron.minute,
        )
