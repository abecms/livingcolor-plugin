"""Mount the plugin exactly the way hermes web_server does, end to end."""
import importlib.util
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def test_full_mount_overview_and_jira(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location(
        "hermes_dashboard_plugin_livingcolor_e2e",
        PLUGIN_ROOT / "dashboard" / "plugin_api.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    app = FastAPI()
    app.include_router(mod.router, prefix="/api/plugins/livingcolor")
    client = TestClient(app)

    assert client.get("/api/plugins/livingcolor/delivery/overview").status_code == 200
    assert client.get("/api/plugins/livingcolor/delivery/readiness").status_code == 200
    assert client.get("/api/plugins/livingcolor/jira/dashboard").status_code != 404
