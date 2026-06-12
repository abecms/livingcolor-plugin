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
def test_append_event_requires_lock_holder(mock_verify):
    mock_verify.return_value = FirebaseUser(
        uid="u1", email="a@b.com", display_name="A", email_verified=True
    )
    store = MagicMock()
    store.append_org_event.return_value = {
        "orgId": "team-1",
        "eventId": "evt-1",
        "event": {"woId": "WO-1", "eventType": "state_change"},
    }
    _override_store(store)
    try:
        client = TestClient(app)
        response = client.post(
            "/v1/orgs/team-1/events",
            headers=AUTH,
            json={"woId": "WO-1", "eventType": "state_change", "payload": {"updatedAt": "2026-06-12T10:00:00Z"}},
        )
    finally:
        _clear_overrides()
    assert response.status_code == 200
    store.append_org_event.assert_called_once()


@patch("cloud_api.auth.verify_firebase_id_token")
def test_reconcile_returns_conflicts(mock_verify):
    mock_verify.return_value = FirebaseUser(
        uid="u1", email="a@b.com", display_name="A", email_verified=True
    )
    store = MagicMock()
    store.reconcile_pending_events.return_value = {
        "orgId": "team-1",
        "accepted": [1],
        "conflicts": [
            {
                "woId": "WO-2",
                "serverVersion": "2026-06-12T12:00:00Z",
                "clientVersion": "2026-06-12T10:00:00Z",
                "localEventId": 2,
            }
        ],
    }
    _override_store(store)
    try:
        client = TestClient(app)
        response = client.post(
            "/v1/orgs/team-1/sync/reconcile",
            headers=AUTH,
            json={
                "events": [
                    {"id": 1, "woId": "WO-1", "payload": {"type": "state_change"}},
                    {"id": 2, "woId": "WO-2", "payload": {"updatedAt": "2026-06-12T10:00:00Z"}},
                ]
            },
        )
    finally:
        _clear_overrides()
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] == [1]
    assert body["conflicts"][0]["woId"] == "WO-2"
