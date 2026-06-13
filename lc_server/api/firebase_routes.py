"""Firebase session and org/project config API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from lc_server.integrations.firebase_auth import (
    FirebaseUser,
    client_firebase_config,
    extract_bearer_token,
    firebase_auth_enabled,
    verify_firebase_id_token,
)
from lc_server.integrations.firestore_store import FirestoreStore

router = APIRouter(tags=["firebase"])


class FirebaseClientConfigResponse(BaseModel):
    enabled: bool
    config: dict[str, str] | None = None


class FirebaseBootstrapResponse(BaseModel):
    enabled: bool = True
    reason: str | None = None
    user: dict[str, Any]
    organizations: list[dict[str, Any]]


class FirebaseDisabledPreferencesResponse(BaseModel):
    enabled: bool = False
    reason: str = "firebase_admin_not_configured"
    orgId: str = "local"
    preferences: dict[str, Any] = {}


class FirebaseDisabledMeResponse(BaseModel):
    enabled: bool = False
    reason: str = "firebase_admin_not_configured"
    user: dict[str, Any] | None = None
    organizations: list[dict[str, Any]] = []


class UserPreferencesUpdate(BaseModel):
    selectedJiraProjectKey: str | None = None


class ProjectConfigUpdate(BaseModel):
    projectName: str | None = None
    mapping: dict[str, Any] | None = None
    deliverySettings: dict[str, Any] | None = None


class CreateTeamOrgBody(BaseModel):
    name: str


class ActiveOrgUpdate(BaseModel):
    orgId: str


class InviteMemberBody(BaseModel):
    email: str
    role: str = "member"


class CreateOrgProjectBody(BaseModel):
    jiraProjectKey: str
    projectName: str


class ShareLocalProjectBody(BaseModel):
    jiraProjectKey: str


def _store() -> FirestoreStore:
    return FirestoreStore()


def _local_mode_bootstrap_response() -> FirebaseBootstrapResponse:
    return FirebaseBootstrapResponse(
        enabled=False,
        reason="local_mode",
        user={
            "uid": "local",
            "email": "",
            "displayName": "Local workspace",
            "activeOrgId": "local",
        },
        organizations=[],
    )


def _require_firebase_user(request: Request) -> FirebaseUser:
    if not firebase_auth_enabled():
        raise HTTPException(
            status_code=503,
            detail="Firebase auth is not configured on this server",
        )
    token = extract_bearer_token(request.headers.get("authorization"))
    if not token:
        raise HTTPException(status_code=401, detail="Missing Firebase ID token")
    try:
        return verify_firebase_id_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid Firebase ID token") from exc


def _optional_firebase_user(request: Request) -> FirebaseUser | None:
    if not firebase_auth_enabled():
        return None
    token = extract_bearer_token(request.headers.get("authorization"))
    if not token:
        return None
    try:
        return verify_firebase_id_token(token)
    except Exception:
        return None


def _active_org_id(request: Request, user: FirebaseUser) -> str:
    store = _store()
    header_org = (request.headers.get("x-org-id") or "").strip()
    if header_org and header_org != "local" and store.is_org_member(header_org, user.uid):
        return header_org
    return store.resolve_active_org_id(user)


def _firebase_client_config_response() -> FirebaseClientConfigResponse:
    config = client_firebase_config()
    return FirebaseClientConfigResponse(enabled=config is not None, config=config)


@router.get("/client-config", response_model=FirebaseClientConfigResponse)
def get_firebase_client_config() -> FirebaseClientConfigResponse:
    return _firebase_client_config_response()


@router.get("/config", response_model=FirebaseClientConfigResponse)
def get_firebase_config() -> FirebaseClientConfigResponse:
    return _firebase_client_config_response()


@router.post("/bootstrap", response_model=FirebaseBootstrapResponse)
def bootstrap_session(request: Request) -> FirebaseBootstrapResponse:
    if not firebase_auth_enabled():
        return _local_mode_bootstrap_response()
    user = _require_firebase_user(request)
    try:
        payload = _store().bootstrap_user(user)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return FirebaseBootstrapResponse(**payload)


@router.get("/me")
def get_me(request: Request) -> dict[str, Any]:
    if not firebase_auth_enabled():
        return FirebaseDisabledMeResponse().model_dump()
    user = _optional_firebase_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Missing Firebase ID token")
    store = _store()
    active_org_id = store.resolve_active_org_id(user)
    return {
        "enabled": True,
        "user": {
            "uid": user.uid,
            "email": user.email,
            "displayName": user.display_name,
            "activeOrgId": active_org_id,
        },
        "organizations": store.list_user_orgs(user.uid),
    }


@router.get("/orgs/{org_id}/projects/{jira_project_key}")
def get_project_config(
    org_id: str,
    jira_project_key: str,
    user: FirebaseUser = Depends(_require_firebase_user),
) -> dict[str, Any]:
    if not _store().is_org_member(org_id, user.uid):
        raise HTTPException(status_code=403, detail="Forbidden")
    doc = _store().get_project_config(org_id, jira_project_key)
    if not doc:
        raise HTTPException(status_code=404, detail="Project config not found")
    return doc


@router.put("/orgs/{org_id}/projects/{jira_project_key}")
def put_project_config(
    org_id: str,
    jira_project_key: str,
    body: ProjectConfigUpdate,
    user: FirebaseUser = Depends(_require_firebase_user),
) -> dict[str, Any]:
    if not _store().is_org_member(org_id, user.uid):
        raise HTTPException(status_code=403, detail="Forbidden")
    payload = body.model_dump(exclude_none=True)
    return _store().save_project_config(org_id, jira_project_key, payload)


@router.get("/preferences")
def get_preferences(request: Request) -> dict[str, Any]:
    if not firebase_auth_enabled():
        return FirebaseDisabledPreferencesResponse().model_dump()
    user = _optional_firebase_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Missing Firebase ID token")
    org_id = _active_org_id(request, user)
    prefs = _store().get_user_preferences(org_id, user.uid) or {}
    return {"enabled": True, "orgId": org_id, "preferences": prefs}


@router.put("/preferences")
def put_preferences(
    request: Request,
    body: UserPreferencesUpdate,
    user: FirebaseUser = Depends(_require_firebase_user),
) -> dict[str, Any]:
    org_id = _active_org_id(request, user)
    prefs = _store().save_user_preferences(
        org_id,
        user.uid,
        body.model_dump(exclude_none=True),
    )
    return {"orgId": org_id, "preferences": prefs}


@router.post("/orgs")
def create_team_org(
    body: CreateTeamOrgBody,
    user: FirebaseUser = Depends(_require_firebase_user),
) -> dict[str, Any]:
    try:
        org = _store().create_team_org(body.name, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return org


@router.put("/me/active-org")
def set_active_org(
    body: ActiveOrgUpdate,
    user: FirebaseUser = Depends(_require_firebase_user),
) -> dict[str, Any]:
    try:
        result = _store().set_active_org(user.uid, body.orgId.strip())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {
        "activeOrgId": result["activeOrgId"],
        "organizations": _store().list_user_orgs(user.uid),
    }


@router.get("/orgs/{org_id}/members")
def list_org_members(
    org_id: str,
    user: FirebaseUser = Depends(_require_firebase_user),
) -> dict[str, Any]:
    if not _store().is_org_member(org_id, user.uid):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"orgId": org_id, "members": _store().list_org_members(org_id)}


@router.post("/orgs/{org_id}/members")
def invite_org_member(
    org_id: str,
    body: InviteMemberBody,
    user: FirebaseUser = Depends(_require_firebase_user),
) -> dict[str, Any]:
    try:
        result = _store().invite_org_member(org_id, body.email, body.role, user.uid)
    except ValueError as exc:
        message = str(exc)
        status = 409 if "already" in message.lower() else 400
        if message == "Admin role required":
            status = 403
        raise HTTPException(status_code=status, detail=message) from exc
    return {"orgId": org_id, **result}


@router.delete("/orgs/{org_id}/members/{member_uid}")
def remove_org_member(
    org_id: str,
    member_uid: str,
    user: FirebaseUser = Depends(_require_firebase_user),
) -> dict[str, Any]:
    try:
        _store().remove_org_member(org_id, member_uid, user.uid)
    except ValueError as exc:
        message = str(exc)
        status = 403 if "Admin" in message or "cannot" in message.lower() else 404
        raise HTTPException(status_code=status, detail=message) from exc
    return {"orgId": org_id, "removedUid": member_uid}


@router.get("/orgs/{org_id}/invites")
def list_org_invites(
    org_id: str,
    user: FirebaseUser = Depends(_require_firebase_user),
) -> dict[str, Any]:
    if not _store().is_org_member(org_id, user.uid):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not _store().is_org_admin(org_id, user.uid):
        raise HTTPException(status_code=403, detail="Admin role required")
    try:
        invites = _store().list_org_invites(org_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"orgId": org_id, "invites": invites}


@router.delete("/orgs/{org_id}/invites/{invite_id}")
def revoke_org_invite(
    org_id: str,
    invite_id: str,
    user: FirebaseUser = Depends(_require_firebase_user),
) -> dict[str, Any]:
    try:
        _store().revoke_org_invite(org_id, invite_id, user.uid)
    except ValueError as exc:
        message = str(exc)
        status = 403 if "Admin" in message else 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return {"orgId": org_id, "revokedInviteId": invite_id}


@router.get("/orgs/{org_id}/projects")
def list_org_projects(
    org_id: str,
    user: FirebaseUser = Depends(_require_firebase_user),
) -> dict[str, Any]:
    if not _store().is_org_member(org_id, user.uid):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"orgId": org_id, "projects": _store().list_org_projects(org_id)}


@router.post("/orgs/{org_id}/projects/share-local")
def share_local_project_to_org(
    org_id: str,
    body: ShareLocalProjectBody,
    user: FirebaseUser = Depends(_require_firebase_user),
) -> dict[str, Any]:
    try:
        project = _store().share_local_project_to_org(org_id, body.jiraProjectKey, user.uid)
    except ValueError as exc:
        message = str(exc)
        status = 403 if message == "Forbidden" else 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return {"orgId": org_id, "project": project}


@router.post("/orgs/{org_id}/projects")
def create_org_project(
    org_id: str,
    body: CreateOrgProjectBody,
    user: FirebaseUser = Depends(_require_firebase_user),
) -> dict[str, Any]:
    try:
        project = _store().create_org_project(
            org_id,
            body.jiraProjectKey,
            body.projectName,
            user.uid,
        )
    except ValueError as exc:
        message = str(exc)
        status = 403 if message == "Forbidden" else 409 if "already exists" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return {"orgId": org_id, "project": project}


@router.delete("/orgs/{org_id}/projects/{jira_project_key}")
def delete_org_project(
    org_id: str,
    jira_project_key: str,
    user: FirebaseUser = Depends(_require_firebase_user),
) -> dict[str, Any]:
    try:
        _store().delete_org_project(org_id, jira_project_key, user.uid)
    except ValueError as exc:
        message = str(exc)
        status = 403 if message == "Forbidden" else 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return {"orgId": org_id, "deletedProjectKey": jira_project_key.strip().upper()}
