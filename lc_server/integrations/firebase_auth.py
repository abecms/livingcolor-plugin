"""Firebase ID token verification for LivingColor API requests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from lc_server.integrations.firebase_admin import (
    _ensure_initialized,
    firebase_admin_configured,
    get_firebase_auth,
)


@dataclass(frozen=True)
class FirebaseUser:
    uid: str
    email: str
    display_name: str
    email_verified: bool


def firebase_auth_enabled() -> bool:
    """True when Firebase Admin is configured and can initialize in this process."""
    return firebase_admin_configured() and _ensure_initialized()


def client_firebase_config() -> dict[str, str] | None:
    """Public web client config for the desktop app (safe to expose)."""
    api_key = os.getenv("NEXT_PUBLIC_FIREBASE_API_KEY", "").strip()
    project_id = os.getenv("NEXT_PUBLIC_FIREBASE_PROJECT_ID", "").strip()
    if not api_key or not project_id:
        return None
    return {
        "apiKey": api_key,
        "authDomain": os.getenv("NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN", "").strip()
        or f"{project_id}.firebaseapp.com",
        "projectId": project_id,
        "storageBucket": os.getenv("NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET", "").strip(),
        "messagingSenderId": os.getenv(
            "NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID", ""
        ).strip(),
        "appId": os.getenv("NEXT_PUBLIC_FIREBASE_APP_ID", "").strip(),
    }


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    token = authorization[len(prefix) :].strip()
    return token or None


def verify_firebase_id_token(token: str) -> FirebaseUser:
    decoded: dict[str, Any] = get_firebase_auth().verify_id_token(token, check_revoked=True)
    email = str(decoded.get("email") or "")
    if not decoded.get("email_verified"):
        raise ValueError("Email not verified")
    return FirebaseUser(
        uid=str(decoded["uid"]),
        email=email,
        display_name=str(decoded.get("name") or email),
        email_verified=True,
    )


def try_verify_firebase_request(authorization: str | None) -> FirebaseUser | None:
    if not firebase_auth_enabled():
        return None
    token = extract_bearer_token(authorization)
    if not token:
        return None
    try:
        return verify_firebase_id_token(token)
    except Exception:
        return None
