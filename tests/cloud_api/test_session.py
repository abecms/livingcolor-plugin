from unittest.mock import patch

from fastapi.testclient import TestClient

from cloud_api.main import app
from lc_server.integrations.firebase_auth import FirebaseUser


def test_bootstrap_requires_auth():
    client = TestClient(app)
    assert client.post("/v1/session/bootstrap").status_code == 401


@patch("cloud_api.routes.session.FirestoreStore")
@patch("cloud_api.auth.verify_firebase_id_token")
def test_bootstrap_returns_orgs(mock_verify, mock_store_cls):
    mock_verify.return_value = FirebaseUser(
        uid="u1",
        email="a@b.com",
        display_name="A",
        email_verified=True,
    )
    mock_store_cls.return_value.bootstrap_user.return_value = {
        "user": {
            "uid": "u1",
            "email": "a@b.com",
            "displayName": "A",
            "activeOrgId": "personal-u1",
        },
        "organizations": [
            {"id": "personal-u1", "name": "Personal", "kind": "personal", "role": "admin"}
        ],
    }
    client = TestClient(app)
    response = client.post(
        "/v1/session/bootstrap",
        headers={"Authorization": "Bearer fake-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["organizations"][0]["kind"] == "personal"


def test_firebase_client_config_endpoint():
    client = TestClient(app)
    response = client.get("/v1/config/firebase-client")
    assert response.status_code == 200
    body = response.json()
    assert "enabled" in body
