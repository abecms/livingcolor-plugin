"""Tests for Firebase Admin bootstrap."""

from __future__ import annotations

import json

from lc_server.integrations import firebase_admin


def test_firebase_admin_configured_from_service_account_file(tmp_path, monkeypatch):
    key_path = tmp_path / "sa.json"
    key_path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": "livingcolor-app",
                "private_key": "-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n",
                "client_email": "test@livingcolor-app.iam.gserviceaccount.com",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("FIREBASE_CLIENT_EMAIL", raising=False)
    monkeypatch.delenv("FIREBASE_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT_PATH", str(key_path))
    assert firebase_admin.firebase_admin_configured() is True

    payload = firebase_admin._load_service_account_dict()
    assert payload["client_email"] == "test@livingcolor-app.iam.gserviceaccount.com"
    assert payload["project_id"] == "livingcolor-app"
