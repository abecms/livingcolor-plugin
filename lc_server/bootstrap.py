"""LivingColor Server bootstrap."""

from __future__ import annotations

import logging

from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.automation.scheduler import DeliveryAutomationScheduler
from lc_server.factory import build_delivery_services

logger = logging.getLogger(__name__)

_bootstrap_done = False
_scheduler: DeliveryAutomationScheduler | None = None


def _run_scheduled_daily_analysis() -> None:
    from delivery_runtime.api import deps

    services = deps.get_services()
    config = load_delivery_automation_config()
    services.pm_inbox.run_daily_analysis(config.project_key)


def _run_scheduled_sprint_report() -> None:
    from delivery_runtime.api import deps

    services = deps.get_services()
    config = load_delivery_automation_config()
    services.pm_inbox.publish_sprint_report(project_key=config.project_key, actor="scheduler")


def bootstrap_livingcolor_server() -> None:
    """Wire delivery runtime API dependencies to server-owned services."""
    global _scheduler, _bootstrap_done
    if _bootstrap_done:
        return

    try:
        from lc_server.integrations.plugin_dependencies import ensure_plugin_python_dependencies

        ensure_plugin_python_dependencies()
    except Exception as exc:
        logger.warning("LivingColor plugin dependency install skipped: %s", exc)

    try:
        from lc_server.env_loader import ensure_livingcolor_env_template

        ensure_livingcolor_env_template()
    except Exception as exc:
        logger.warning("LivingColor env template setup skipped: %s", exc)

    from jira_dashboard.compat import install_hermes_cli_jira_dashboard_shim

    install_hermes_cli_jira_dashboard_shim()

    from lc_server.env_loader import prepare_delivery_agent_environment

    prepare_delivery_agent_environment()

    try:
        from lc_server.integrations.mcp_env_bootstrap import ensure_mcp_servers_from_env

        ensure_mcp_servers_from_env()
    except Exception as exc:
        logger.warning("MCP env bootstrap skipped: %s", exc)

    from delivery_runtime.api import deps
    from delivery_runtime.persistence.db import init_db

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
        from lc_server.integrations.project_chat_context import install_project_chat_context_hooks
        from lc_server.integrations.livingcolor_pm_profile import ensure_livingcolor_pm_profile

        ensure_livingcolor_pm_profile()
        install_project_chat_context_hooks()
    except Exception as exc:
        logger.warning("Could not install LivingColor project chat hooks: %s", exc)

    try:
        from lc_server.integrations.mcp_warmup import warm_configured_mcp_connections

        warm_configured_mcp_connections()
    except Exception as exc:
        logger.warning("MCP warm connect on startup skipped: %s", exc)

    config = load_delivery_automation_config()
    if config.daily_analysis_cron.enabled or config.sprint_report_cron.enabled:
        _scheduler = DeliveryAutomationScheduler(
            daily_runner=_run_scheduled_daily_analysis,
            sprint_report_runner=_run_scheduled_sprint_report
            if config.sprint_report_cron.enabled
            else None,
        )
        _scheduler.start()
        if config.daily_analysis_cron.enabled:
            logger.info(
                "Daily analysis scheduler enabled for %s at %02d:%02d UTC",
                config.project_key,
                config.daily_analysis_cron.hour,
                config.daily_analysis_cron.minute,
            )
        if config.sprint_report_cron.enabled:
            logger.info(
                "Sprint report scheduler enabled for %s at %02d:%02d UTC",
                config.project_key,
                config.sprint_report_cron.hour,
                config.sprint_report_cron.minute,
            )
    _bootstrap_done = True
