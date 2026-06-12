from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from cloud_api.auth import require_user
from cloud_api.deps import get_store, resolve_active_org_id
from cloud_api.models import ActiveOrgUpdate, CreateTeamOrgBody, InviteMemberBody, UserPreferencesUpdate
from lc_server.integrations.firebase_auth import FirebaseUser
from lc_server.integrations.firestore_store import FirestoreStore

router = APIRouter(tags=["orgs"])


@router.get("/orgs")
def list_orgs(user: FirebaseUser = Depends(require_user)) -> dict[str, Any]:
    store = get_store()
    return {"organizations": store.list_user_orgs(user.uid)}


@router.post("/orgs")
def create_team_org(
    body: CreateTeamOrgBody,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        org = store.create_team_org(body.name, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return org


@router.put("/me/active-org")
def set_active_org(
    body: ActiveOrgUpdate,
    user: FirebaseUser = Depends(require_user),
) -> dict[str, Any]:
    store = get_store()
    try:
        result = store.set_active_org(user.uid, body.orgId.strip())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {
        "activeOrgId": result["activeOrgId"],
        "organizations": store.list_user_orgs(user.uid),
    }


@router.get("/preferences")
def get_preferences(
    request: Request,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    org_id = resolve_active_org_id(request, user, store)
    prefs = store.get_user_preferences(org_id, user.uid) or {}
    return {"orgId": org_id, "preferences": prefs}


@router.put("/preferences")
def put_preferences(
    request: Request,
    body: UserPreferencesUpdate,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    org_id = resolve_active_org_id(request, user, store)
    prefs = store.save_user_preferences(org_id, user.uid, body.model_dump(exclude_none=True))
    return {"orgId": org_id, "preferences": prefs}


@router.get("/orgs/{org_id}/members")
def list_org_members(
    org_id: str,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    if not store.is_org_member(org_id, user.uid):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"orgId": org_id, "members": store.list_org_members(org_id)}


@router.post("/orgs/{org_id}/invites")
def invite_org_member(
    org_id: str,
    body: InviteMemberBody,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        result = store.invite_org_member(org_id, body.email, body.role, user.uid)
    except ValueError as exc:
        message = str(exc)
        status = 409 if "already" in message.lower() else 400
        if message == "Admin role required":
            status = 403
        raise HTTPException(status_code=status, detail=message) from exc
    return {"orgId": org_id, **result}


@router.post("/orgs/{org_id}/members")
def invite_org_member_legacy_path(
    org_id: str,
    body: InviteMemberBody,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    return invite_org_member(org_id, body, user, store)


@router.delete("/orgs/{org_id}/members/{member_uid}")
def remove_org_member(
    org_id: str,
    member_uid: str,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        store.remove_org_member(org_id, member_uid, user.uid)
    except ValueError as exc:
        message = str(exc)
        status = 403 if "Admin" in message or "cannot" in message.lower() else 404
        raise HTTPException(status_code=status, detail=message) from exc
    return {"orgId": org_id, "removedUid": member_uid}


@router.get("/orgs/{org_id}/invites")
def list_org_invites(
    org_id: str,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    if not store.is_org_member(org_id, user.uid):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not store.is_org_admin(org_id, user.uid):
        raise HTTPException(status_code=403, detail="Admin role required")
    try:
        invites = store.list_org_invites(org_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"orgId": org_id, "invites": invites}


@router.delete("/orgs/{org_id}/invites/{invite_id}")
def revoke_org_invite(
    org_id: str,
    invite_id: str,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        store.revoke_org_invite(org_id, invite_id, user.uid)
    except ValueError as exc:
        message = str(exc)
        status = 403 if "Admin" in message else 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return {"orgId": org_id, "revokedInviteId": invite_id}
