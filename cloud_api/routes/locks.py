from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cloud_api.auth import require_user
from cloud_api.deps import get_store
from lc_server.integrations.firebase_auth import FirebaseUser
from lc_server.integrations.firestore_store import FirestoreStore

router = APIRouter(tags=["locks"])


class AcquireLockBody(BaseModel):
    sessionId: str | None = None


def _lock_error_status(message: str) -> int:
    if message == "Forbidden":
        return 403
    if "held by another" in message.lower():
        return 409
    return 400


@router.post("/orgs/{org_id}/work-orders/{wo_id}/lock")
def acquire_work_order_lock(
    org_id: str,
    wo_id: str,
    body: AcquireLockBody | None = None,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        return store.acquire_work_order_lock(
            org_id,
            wo_id,
            user,
            body.sessionId if body else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=_lock_error_status(str(exc)), detail=str(exc)) from exc


@router.delete("/orgs/{org_id}/work-orders/{wo_id}/lock")
def release_work_order_lock(
    org_id: str,
    wo_id: str,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        return store.release_work_order_lock(org_id, wo_id, user)
    except ValueError as exc:
        status = 403 if "held by another" in str(exc).lower() else _lock_error_status(str(exc))
        raise HTTPException(status_code=status, detail=str(exc)) from exc
