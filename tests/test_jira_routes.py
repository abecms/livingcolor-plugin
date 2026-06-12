from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_jira_router_mounts_and_dashboard_endpoint_exists():
    from jira_dashboard.routes import router

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/livingcolor/jira")
    client = TestClient(app)
    resp = client.get("/api/plugins/livingcolor/jira/dashboard")
    assert resp.status_code != 404
