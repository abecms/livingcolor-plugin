from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cloud_api.auth import require_user
from lc_server.integrations.firebase_auth import FirebaseUser, client_firebase_config
from lc_server.integrations.firestore_store import FirestoreStore

router = APIRouter(tags=["session"])


class FirebaseClientConfigResponse(BaseModel):
    enabled: bool
    config: dict[str, str] | None = None


class FirebaseBootstrapResponse(BaseModel):
    user: dict[str, Any]
    organizations: list[dict[str, Any]]


@router.get("/config/firebase-client", response_model=FirebaseClientConfigResponse)
def get_firebase_client_config() -> FirebaseClientConfigResponse:
    config = client_firebase_config()
    return FirebaseClientConfigResponse(enabled=config is not None, config=config)


@router.get("/me")
def get_me(user: FirebaseUser = Depends(require_user)) -> dict[str, Any]:
    store = FirestoreStore()
    active_org_id = store.resolve_active_org_id(user)
    return {
        "user": {
            "uid": user.uid,
            "email": user.email,
            "displayName": user.display_name,
            "activeOrgId": active_org_id,
        },
        "organizations": store.list_user_orgs(user.uid),
    }


@router.post("/session/bootstrap", response_model=FirebaseBootstrapResponse)
def bootstrap_session(user: FirebaseUser = Depends(require_user)) -> FirebaseBootstrapResponse:
    try:
        payload = FirestoreStore().bootstrap_user(user)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return FirebaseBootstrapResponse(**payload)
