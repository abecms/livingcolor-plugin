"""Background orchestrator scheduling tests."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from delivery_runtime.orchestration.background import schedule_orchestrator_tick, wait_for_orchestrator_ticks


class _SlowOrchestrator:
    def __init__(self) -> None:
        self.started = False
        self.finished = False

    def tick(self, work_order_id: str) -> list[str]:
        self.started = True
        time.sleep(0.2)
        self.finished = True
        return [work_order_id]


def test_schedule_orchestrator_tick_runs_in_background_when_not_sync(monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_SYNC_ORCHESTRATOR", raising=False)
    orchestrator = _SlowOrchestrator()

    schedule_orchestrator_tick(orchestrator, "WO-1")

    assert orchestrator.started is True
    assert orchestrator.finished is False
    wait_for_orchestrator_ticks(timeout=2)
    assert orchestrator.finished is True


def test_schedule_orchestrator_tick_runs_inline_in_sync_mode(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_SYNC_ORCHESTRATOR", "1")
    orchestrator = MagicMock()
    orchestrator.tick.return_value = ["WO-2"]

    schedule_orchestrator_tick(orchestrator, "WO-2")

    orchestrator.tick.assert_called_once_with("WO-2")
