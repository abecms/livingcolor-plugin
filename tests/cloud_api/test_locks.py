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
def test_acquire_lock_exclusive(mock_verify):
    mock_verify.return_value = FirebaseUser(
        uid="u1", email="a@b.com", display_name="A", email_verified=True
    )
    store = MagicMock()
    store.acquire_work_order_lock.return_value = {
        "orgId": "team-1",
        "workOrderId": "WO-1",
        "lock": {"holderUid": "u1", "holderEmail": "a@b.com"},
    }
    _override_store(store)
    try:
        client = TestClient(app)
        response = client.post(
            "/v1/orgs/team-1/work-orders/WO-1/lock",
            headers=AUTH,
            json={"sessionId": "sess-1"},
        )
    finally:
        _clear_overrides()
    assert response.status_code == 200
    assert response.json()["lock"]["holderUid"] == "u1"


@patch("cloud_api.auth.verify_firebase_id_token")
def test_acquire_lock_conflict(mock_verify):
    mock_verify.return_value = FirebaseUser(
        uid="u2", email="b@b.com", display_name="B", email_verified=True
    )
    store = MagicMock()
    store.acquire_work_order_lock.side_effect = ValueError("Lock held by another member")
    _override_store(store)
    try:
        client = TestClient(app)
        response = client.post("/v1/orgs/team-1/work-orders/WO-1/lock", headers=AUTH)
    finally:
        _clear_overrides()
    assert response.status_code == 409


@patch("cloud_api.auth.verify_firebase_id_token")
def test_release_lock_only_holder(mock_verify):
    mock_verify.return_value = FirebaseUser(
        uid="u1", email="a@b.com", display_name="A", email_verified=True
    )
    store = MagicMock()
    store.release_work_order_lock.return_value = {
        "orgId": "team-1",
        "workOrderId": "WO-1",
        "released": True,
    }
    _override_store(store)
    try:
        client = TestClient(app)
        ok = client.delete("/v1/orgs/team-1/work-orders/WO-1/lock", headers=AUTH)
    finally:
        _clear_overrides()
    assert ok.status_code == 200

    store.release_work_order_lock.side_effect = ValueError("Lock held by another member")
    _override_store(store)
    try:
        client = TestClient(app)
        forbidden = client.delete("/v1/orgs/team-1/work-orders/WO-1/lock", headers=AUTH)
    finally:
        _clear_overrides()
    assert forbidden.status_code == 403
