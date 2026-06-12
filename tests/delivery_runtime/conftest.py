"""Delivery runtime test defaults."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _heuristic_developer_backend(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_DEVELOPER_BACKEND", "heuristic")


@pytest.fixture(autouse=True)
def _sync_orchestrator_in_tests(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_SYNC_ORCHESTRATOR", "1")
