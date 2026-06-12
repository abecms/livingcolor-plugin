"""Firebase ID token verification for cloud API requests."""

from __future__ import annotations

from fastapi import HTTPException, Request

from lc_server.integrations.firebase_auth import (
    FirebaseUser,
    extract_bearer_token,
    verify_firebase_id_token,
)


def require_user(request: Request) -> FirebaseUser:
    token = extract_bearer_token(request.headers.get("authorization"))
    if not token:
        raise HTTPException(status_code=401, detail="Missing Firebase ID token")
    try:
        return verify_firebase_id_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid Firebase ID token") from exc
