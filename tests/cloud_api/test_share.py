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
def test_share_from_local_creates_project(mock_verify):
    mock_verify.return_value = FirebaseUser(
        uid="u1", email="a@b.com", display_name="A", email_verified=True
    )
    store = MagicMock()
    store.save_project_config.return_value = {
        "jiraProjectKey": "BN",
        "projectName": "BN",
        "sharedFromLocal": True,
    }
    _override_store(store)
    try:
        client = TestClient(app)
        response = client.post(
            "/v1/orgs/org1/projects/BN/share-from-local",
            headers=AUTH,
            json={
                "jiraProjectKey": "BN",
                "projectName": "BN",
                "mapping": {"default_repo": "gitlab.com/client/bn"},
                "deliverySettings": {"sprintDurationDays": 14},
            },
        )
    finally:
        _clear_overrides()
    assert response.status_code == 200
    assert response.json()["project"]["jiraProjectKey"] == "BN"
    store.append_org_audit_event.assert_called_once()
