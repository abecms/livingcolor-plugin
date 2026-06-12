"""Tests for Firebase auth helpers."""

from __future__ import annotations

import pytest

from lc_server.integrations import firebase_auth


def test_extract_bearer_token():
    assert firebase_auth.extract_bearer_token(None) is None
    assert firebase_auth.extract_bearer_token("Basic abc") is None
    assert firebase_auth.extract_bearer_token("Bearer token-123") == "token-123"


def test_client_firebase_config_missing(monkeypatch):
    monkeypatch.delenv("NEXT_PUBLIC_FIREBASE_API_KEY", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_FIREBASE_PROJECT_ID", raising=False)
    assert firebase_auth.client_firebase_config() is None


def test_client_firebase_config_present(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_FIREBASE_API_KEY", "test-key")
    monkeypatch.setenv("NEXT_PUBLIC_FIREBASE_PROJECT_ID", "livingcolor-app")
    config = firebase_auth.client_firebase_config()
    assert config is not None
    assert config["apiKey"] == "test-key"
    assert config["projectId"] == "livingcolor-app"
    assert config["authDomain"] == "livingcolor-app.firebaseapp.com"


def test_try_verify_firebase_request_disabled(monkeypatch):
    monkeypatch.setattr(firebase_auth, "firebase_auth_enabled", lambda: False)
    assert firebase_auth.try_verify_firebase_request("Bearer x") is None


def test_try_verify_firebase_request_invalid_token(monkeypatch):
    monkeypatch.setattr(firebase_auth, "firebase_auth_enabled", lambda: True)

    class FakeAuth:
        def verify_id_token(self, token, check_revoked=True):
            raise ValueError("bad token")

    monkeypatch.setattr(firebase_auth, "get_firebase_auth", lambda: FakeAuth())
    assert firebase_auth.try_verify_firebase_request("Bearer bad") is None


def test_verify_firebase_id_token_success(monkeypatch):
    class FakeAuth:
        def verify_id_token(self, token, check_revoked=True):
            assert token == "good"
            return {
                "uid": "uid-1",
                "email": "user@example.com",
                "name": "User",
                "email_verified": True,
            }

    monkeypatch.setattr(firebase_auth, "get_firebase_auth", lambda: FakeAuth())
    user = firebase_auth.verify_firebase_id_token("good")
    assert user.uid == "uid-1"
    assert user.email == "user@example.com"
    assert user.display_name == "User"


def test_verify_firebase_id_token_unverified_email(monkeypatch):
    class FakeAuth:
        def verify_id_token(self, token, check_revoked=True):
            return {"uid": "uid-1", "email": "user@example.com", "email_verified": False}

    monkeypatch.setattr(firebase_auth, "get_firebase_auth", lambda: FakeAuth())
    with pytest.raises(ValueError, match="Email not verified"):
        firebase_auth.verify_firebase_id_token("token")
