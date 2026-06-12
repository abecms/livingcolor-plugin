"""Firebase Admin SDK bootstrap for LivingColor Server."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from firebase_admin.auth import Auth  # noqa: F401
    from google.cloud.firestore import Client as FirestoreClient  # noqa: F401

_db: FirestoreClient | None = None
_auth: Auth | None = None
_init_attempted = False


def _service_account_path() -> Path | None:
    for key in ("FIREBASE_SERVICE_ACCOUNT_PATH", "GOOGLE_APPLICATION_CREDENTIALS"):
        raw = os.getenv(key, "").strip()
        if raw:
            path = Path(raw).expanduser()
            if path.is_file():
                return path
    return None


def _project_id() -> str:
    return (
        os.getenv("FIREBASE_PROJECT_ID", "").strip()
        or os.getenv("NEXT_PUBLIC_FIREBASE_PROJECT_ID", "").strip()
        or "livingcolor-app"
    )


def _normalize_private_key(raw: str) -> str:
    key = raw.strip()
    if key.startswith('"') and key.endswith('"'):
        key = key[1:-1]
    if "\\n" in key:
        key = key.replace("\\n", "\n")
    return key


def firebase_admin_configured() -> bool:
    if _service_account_path() is not None:
        return True
    project_id = _project_id()
    client_email = os.getenv("FIREBASE_CLIENT_EMAIL", "").strip()
    private_key = os.getenv("FIREBASE_PRIVATE_KEY", "").strip()
    return bool(project_id and client_email and private_key)


def _load_service_account_dict() -> dict[str, str]:
    path = _service_account_path()
    if path is not None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            "type": str(payload.get("type") or "service_account"),
            "project_id": str(payload.get("project_id") or _project_id()),
            "private_key": str(payload["private_key"]),
            "client_email": str(payload["client_email"]),
            "token_uri": str(payload.get("token_uri") or "https://oauth2.googleapis.com/token"),
        }

    return {
        "type": "service_account",
        "project_id": _project_id(),
        "private_key": _normalize_private_key(os.environ["FIREBASE_PRIVATE_KEY"]),
        "client_email": os.environ["FIREBASE_CLIENT_EMAIL"].strip(),
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def _ensure_initialized() -> bool:
    global _db, _auth, _init_attempted
    if _db is not None and _auth is not None:
        return True
    if _init_attempted and (_db is None or _auth is None):
        return False
    _init_attempted = True

    if not firebase_admin_configured():
        return False

    try:
        import firebase_admin
        from firebase_admin import auth, credentials, firestore
    except ImportError:
        return False

    if not firebase_admin._apps:
        account = _load_service_account_dict()
        cred = credentials.Certificate(account)
        firebase_admin.initialize_app(cred, {"projectId": account["project_id"]})

    _db = firestore.client()
    _auth = auth
    return True


def get_firestore():
    if not _ensure_initialized():
        raise RuntimeError(
            "Firebase Admin is not configured. Set FIREBASE_SERVICE_ACCOUNT_PATH "
            "(or GOOGLE_APPLICATION_CREDENTIALS), or FIREBASE_PROJECT_ID + "
            "FIREBASE_CLIENT_EMAIL + FIREBASE_PRIVATE_KEY."
        )
    assert _db is not None
    return _db


def get_firebase_auth():
    if not _ensure_initialized():
        raise RuntimeError("Firebase Admin is not configured.")
    assert _auth is not None
    return _auth
