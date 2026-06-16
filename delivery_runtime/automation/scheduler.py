"""Background scheduler for LivingColor delivery automation."""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import Callable

from delivery_runtime.automation.config import load_delivery_automation_config

logger = logging.getLogger(__name__)

_tick_lock = threading.Lock()
_last_daily_run_key: str | None = None
_last_sprint_report_run_key: str | None = None


def _today_run_key(*, project_key: str, hour: int, minute: int, prefix: str = "daily") -> str:
    now = datetime.now(UTC)
    return f"{prefix}:{project_key}:{now.date().isoformat()}:{hour:02d}:{minute:02d}"


def should_run_daily_analysis(now: datetime | None = None) -> bool:
    config = load_delivery_automation_config()
    if not config.daily_analysis_cron.enabled:
        return False

    current = now or datetime.now(UTC)
    return (
        current.hour == config.daily_analysis_cron.hour
        and current.minute == config.daily_analysis_cron.minute
    )


def run_daily_analysis_if_due(
    runner: Callable[[], None],
    *,
    now: datetime | None = None,
    force: bool = False,
) -> bool:
    """Execute the daily analysis runner once per scheduled slot."""
    global _last_daily_run_key

    config = load_delivery_automation_config()
    if not force and not should_run_daily_analysis(now):
        return False

    run_key = _today_run_key(
        project_key=config.project_key,
        hour=config.daily_analysis_cron.hour,
        minute=config.daily_analysis_cron.minute,
        prefix="daily",
    )
    with _tick_lock:
        if _last_daily_run_key == run_key:
            return False
        _last_daily_run_key = run_key

    logger.info(
        "Starting scheduled daily analysis for project %s",
        config.project_key,
    )
    runner()
    return True


def should_run_sprint_report(now: datetime | None = None) -> bool:
    from delivery_runtime.pm_inbox.sprint_report import should_run_scheduled_sprint_report

    config = load_delivery_automation_config()
    if not config.sprint_report_cron.enabled:
        return False
    return should_run_scheduled_sprint_report(project_key=config.project_key, now=now)


def run_sprint_report_if_due(
    runner: Callable[[], None],
    *,
    now: datetime | None = None,
    force: bool = False,
) -> bool:
    """Execute the sprint report runner once per scheduled slot on sprint end day."""
    global _last_sprint_report_run_key

    config = load_delivery_automation_config()
    if not force and not should_run_sprint_report(now):
        return False

    run_key = _today_run_key(
        project_key=config.project_key,
        hour=config.sprint_report_cron.hour,
        minute=config.sprint_report_cron.minute,
        prefix="sprint-report",
    )
    with _tick_lock:
        if _last_sprint_report_run_key == run_key:
            return False
        _last_sprint_report_run_key = run_key

    logger.info(
        "Starting scheduled sprint report for project %s",
        config.project_key,
    )
    runner()
    return True


class DeliveryAutomationScheduler:
    """Minute-resolution scheduler for LivingColor background jobs."""

    def __init__(
        self,
        *,
        daily_runner: Callable[[], None],
        sprint_report_runner: Callable[[], None] | None = None,
        poll_seconds: int = 30,
    ) -> None:
        self._daily_runner = daily_runner
        self._sprint_report_runner = sprint_report_runner
        self._poll_seconds = max(5, poll_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="livingcolor-delivery-automation",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                run_daily_analysis_if_due(self._daily_runner)
                if self._sprint_report_runner is not None:
                    run_sprint_report_if_due(self._sprint_report_runner)
            except Exception:
                logger.exception("Scheduled delivery automation failed")
            self._stop.wait(self._poll_seconds)


class DailyAnalysisScheduler(DeliveryAutomationScheduler):
    """Backward-compatible alias for the daily analysis scheduler."""

    def __init__(self, *, runner: Callable[[], None], poll_seconds: int = 30) -> None:
        super().__init__(daily_runner=runner, sprint_report_runner=None, poll_seconds=poll_seconds)
