from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cloud_api.auth import require_user
from cloud_api.deps import get_store
from lc_server.integrations.firebase_auth import FirebaseUser
from lc_server.integrations.firestore_store import FirestoreStore

router = APIRouter(tags=["reconcile"])


class PendingEventBody(BaseModel):
    id: int | str | None = None
    woId: str
    payload: dict[str, Any] | None = None


class ReconcileBody(BaseModel):
    events: list[PendingEventBody] = []


@router.post("/orgs/{org_id}/sync/reconcile")
def reconcile_pending_events(
    org_id: str,
    body: ReconcileBody,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        events = [item.model_dump() for item in body.events]
        return store.reconcile_pending_events(org_id, user, events)
    except ValueError as exc:
        message = str(exc)
        status = 403 if message == "Forbidden" else 400
        raise HTTPException(status_code=status, detail=message) from exc
