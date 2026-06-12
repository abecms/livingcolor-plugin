from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from cloud_api.deps import get_store
from cloud_api.main import app
from lc_server.integrations.firebase_auth import FirebaseUser

AUTH = {"Authorization": "Bearer fake-token"}


def _override_store(mock_store: MagicMock):
    app.dependency_overrides[get_store] = lambda: mock_store


def _clear_overrides():
    app.dependency_overrides.clear()


@patch("cloud_api.auth.verify_firebase_id_token")
def test_create_team_org(mock_verify):
    mock_verify.return_value = FirebaseUser(
        uid="u1", email="a@b.com", display_name="A", email_verified=True
    )
    store = MagicMock()
    store.create_team_org.return_value = {
        "id": "team-1",
        "name": "Acme",
        "kind": "team",
        "role": "admin",
    }
    _override_store(store)
    try:
        client = TestClient(app)
        response = client.post("/v1/orgs", json={"name": "Acme"}, headers=AUTH)
    finally:
        _clear_overrides()
    assert response.status_code == 200
    assert response.json()["kind"] == "team"


@patch("cloud_api.auth.verify_firebase_id_token")
def test_list_org_members_forbidden(mock_verify):
    mock_verify.return_value = FirebaseUser(
        uid="u1", email="a@b.com", display_name="A", email_verified=True
    )
    store = MagicMock()
    store.is_org_member.return_value = False
    _override_store(store)
    try:
        client = TestClient(app)
        response = client.get("/v1/orgs/team-1/members", headers=AUTH)
    finally:
        _clear_overrides()
    assert response.status_code == 403


@patch("cloud_api.auth.verify_firebase_id_token")
def test_list_org_projects(mock_verify):
    mock_verify.return_value = FirebaseUser(
        uid="u1", email="a@b.com", display_name="A", email_verified=True
    )
    store = MagicMock()
    store.is_org_member.return_value = True
    store.list_org_projects.return_value = [{"jiraProjectKey": "BN", "projectName": "BN"}]
    _override_store(store)
    try:
        client = TestClient(app)
        response = client.get("/v1/orgs/team-1/projects", headers=AUTH)
    finally:
        _clear_overrides()
    assert response.status_code == 200
    assert response.json()["projects"][0]["jiraProjectKey"] == "BN"
