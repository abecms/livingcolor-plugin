import importlib.util
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _load_plugin_api(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location(
        "hermes_dashboard_plugin_livingcolor",
        PLUGIN_ROOT / "dashboard" / "plugin_api.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_dashboard_plugin_livingcolor"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_router_serves_delivery_overview(monkeypatch, tmp_path):
    mod = _load_plugin_api(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/plugins/livingcolor")
    client = TestClient(app)
    resp = client.get("/api/plugins/livingcolor/delivery/overview")
    assert resp.status_code == 200


def test_router_serves_jira_namespace(monkeypatch, tmp_path):
    mod = _load_plugin_api(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/plugins/livingcolor")
    client = TestClient(app)
    assert client.get("/api/plugins/livingcolor/jira/dashboard").status_code != 404
