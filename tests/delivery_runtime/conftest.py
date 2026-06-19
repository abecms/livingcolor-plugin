"""Delivery runtime test defaults."""

from __future__ import annotations

import pytest

from delivery_http_client import mount_livingcolor_api_routes

__all__ = ["mount_livingcolor_api_routes", "livingcolor_home"]


@pytest.fixture
def livingcolor_home(tmp_path, monkeypatch):
    """Plugin data home at HERMES_HOME/livingcolor (see lc_constants)."""
    hermes_home = tmp_path / "hermes"
    lc_home = hermes_home / "livingcolor"
    lc_home.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    return lc_home


@pytest.fixture(autouse=True)
def _heuristic_developer_backend(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_DEVELOPER_BACKEND", "heuristic")


@pytest.fixture(autouse=True)
def _sync_orchestrator_in_tests(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_SYNC_ORCHESTRATOR", "1")
