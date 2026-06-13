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


def test_bootstrap_returns_disabled_when_firebase_admin_missing(monkeypatch):
    monkeypatch.setattr(
        "lc_server.api.firebase_routes.firebase_auth_enabled",
        lambda: False,
    )
    from dashboard.plugin_api import router

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/livingcolor")
    client = TestClient(app)
    response = client.post("/api/plugins/livingcolor/firebase/bootstrap")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["reason"] == "local_mode"
    assert body["user"]["activeOrgId"] == "local"
    assert body["organizations"] == []


def test_bootstrap_returns_local_mode_when_firebase_admin_unconfigured(monkeypatch):
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("FIREBASE_CLIENT_EMAIL", raising=False)
    monkeypatch.delenv("FIREBASE_PRIVATE_KEY", raising=False)
    monkeypatch.setattr(
        "lc_server.integrations.firebase_admin._default_service_account_candidates",
        lambda: [],
    )

    from dashboard.plugin_api import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/livingcolor")
    client = TestClient(app)
    response = client.post("/api/plugins/livingcolor/firebase/bootstrap")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["user"]["activeOrgId"] == "local"
    assert body["organizations"] == []


def test_preferences_returns_local_mode_when_firebase_admin_unconfigured(monkeypatch):
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("FIREBASE_CLIENT_EMAIL", raising=False)
    monkeypatch.delenv("FIREBASE_PRIVATE_KEY", raising=False)
    monkeypatch.setattr(
        "lc_server.integrations.firebase_admin._default_service_account_candidates",
        lambda: [],
    )

    from dashboard.plugin_api import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/livingcolor")
    client = TestClient(app)
    response = client.get("/api/plugins/livingcolor/firebase/preferences")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["orgId"] == "local"


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
