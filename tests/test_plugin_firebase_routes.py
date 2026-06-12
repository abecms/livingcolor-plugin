from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_client_config_route_is_mounted():
    from dashboard.plugin_api import router

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/livingcolor")
    client = TestClient(app)
    response = client.get("/api/plugins/livingcolor/firebase/client-config")
    assert response.status_code == 200
    body = response.json()
    assert "enabled" in body


def test_client_config_returns_embedded_defaults_when_env_set(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_FIREBASE_API_KEY", "AIzaSy-test")
    monkeypatch.setenv("NEXT_PUBLIC_FIREBASE_PROJECT_ID", "livingcolor-app")
    from dashboard.plugin_api import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/livingcolor")
    client = TestClient(app)
    response = client.get("/api/plugins/livingcolor/firebase/client-config")
    assert response.status_code == 200
    body = response.json()
    assert body["config"]["projectId"] == "livingcolor-app"
