"""Run orchestration ticks off the HTTP request thread."""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_active_threads: list[threading.Thread] = []
_lock = threading.Lock()
_tick_execution_lock = threading.Lock()


def orchestrator_ticks_sync() -> bool:
    return os.getenv("LIVINGCOLOR_SYNC_ORCHESTRATOR", "").strip().lower() in {"1", "true", "yes", "on"}


def schedule_orchestrator_tick(orchestrator, work_order_id: str) -> None:
    """Advance a work order without blocking API handlers on long agent runs."""
    if not orchestrator or not work_order_id:
        return
    if orchestrator_ticks_sync():
        with _tick_execution_lock:
            orchestrator.tick(work_order_id)
        return

    def _run() -> None:
        try:
            with _tick_execution_lock:
                orchestrator.tick(work_order_id)
        except Exception:
            logger.exception("Background orchestrator tick failed for %s", work_order_id)

    thread = threading.Thread(
        target=_run,
        name=f"orchestrator-tick-{work_order_id}",
        daemon=True,
    )
    with _lock:
        _active_threads[:] = [item for item in _active_threads if item.is_alive()]
        _active_threads.append(thread)
    thread.start()


def wait_for_orchestrator_ticks(timeout: float = 30.0) -> None:
    """Test helper: block until background orchestrator threads finish."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _lock:
            alive = [item for item in _active_threads if item.is_alive()]
            _active_threads[:] = alive
            if not alive:
                return
        time.sleep(0.05)
    raise TimeoutError("Timed out waiting for background orchestrator ticks")
