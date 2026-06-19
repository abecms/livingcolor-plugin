"""Shared HTTP test client helpers for delivery runtime API tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def mount_livingcolor_api_routes(app) -> None:
    """Mount LivingColor plugin routes on a FastAPI app for HTTP API tests."""
    if getattr(app.state, "_livingcolor_api_mounted", False):
        return
    spec = importlib.util.spec_from_file_location(
        "hermes_dashboard_plugin_livingcolor_test",
        _REPO_ROOT / "dashboard" / "plugin_api.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load dashboard/plugin_api.py for tests")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_dashboard_plugin_livingcolor_test"] = mod
    spec.loader.exec_module(mod)
    original_routes = list(app.router.routes)
    app.include_router(mod.router, prefix="/api")
    new_routes = [route for route in app.router.routes if route not in original_routes]
    for route in new_routes:
        app.router.routes.remove(route)
    for offset, route in enumerate(new_routes):
        app.router.routes.insert(offset, route)
    app.state._livingcolor_api_mounted = True


def delivery_api_client():
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi/starlette not installed")

    from delivery_runtime.persistence.db import init_db
    from hermes_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN, app

    init_db()
    mount_livingcolor_api_routes(app)
    client = TestClient(app)
    client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return client
