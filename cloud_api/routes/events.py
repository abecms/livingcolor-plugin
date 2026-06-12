from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cloud_api.auth import require_user
from cloud_api.deps import get_store
from lc_server.integrations.firebase_auth import FirebaseUser
from lc_server.integrations.firestore_store import FirestoreStore

router = APIRouter(tags=["events"])


class AppendEventBody(BaseModel):
    woId: str
    eventType: str = "state_change"
    payload: dict[str, Any] | None = None


def _event_error_status(message: str) -> int:
    if message == "Forbidden":
        return 403
    if "held by another" in message.lower():
        return 409
    return 400


@router.post("/orgs/{org_id}/events")
def append_org_event(
    org_id: str,
    body: AppendEventBody,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        return store.append_org_event(
            org_id,
            user,
            body.woId,
            body.eventType,
            body.payload or {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=_event_error_status(str(exc)), detail=str(exc)) from exc
