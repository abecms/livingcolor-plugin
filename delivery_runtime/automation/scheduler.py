"""Background scheduler for LivingColor daily delivery analysis."""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import Callable

from delivery_runtime.automation.config import load_delivery_automation_config

logger = logging.getLogger(__name__)

_tick_lock = threading.Lock()
_last_run_key: str | None = None


def _today_run_key(*, project_key: str, hour: int, minute: int) -> str:
    now = datetime.now(UTC)
    return f"{project_key}:{now.date().isoformat()}:{hour:02d}:{minute:02d}"


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
    global _last_run_key

    config = load_delivery_automation_config()
    if not force and not should_run_daily_analysis(now):
        return False

    run_key = _today_run_key(
        project_key=config.project_key,
        hour=config.daily_analysis_cron.hour,
        minute=config.daily_analysis_cron.minute,
    )
    with _tick_lock:
        if _last_run_key == run_key:
            return False
        _last_run_key = run_key

    logger.info(
        "Starting scheduled daily analysis for project %s",
        config.project_key,
    )
    runner()
    return True


class DailyAnalysisScheduler:
    """Simple minute-resolution scheduler for the LivingColor server process."""

    def __init__(
        self,
        *,
        runner: Callable[[], None],
        poll_seconds: int = 30,
    ) -> None:
        self._runner = runner
        self._poll_seconds = max(5, poll_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="livingcolor-daily-analysis",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                run_daily_analysis_if_due(self._runner)
            except Exception:
                logger.exception("Scheduled daily analysis failed")
            self._stop.wait(self._poll_seconds)
