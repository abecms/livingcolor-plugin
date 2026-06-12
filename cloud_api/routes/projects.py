from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from cloud_api.auth import require_user
from cloud_api.deps import get_store
from cloud_api.models import CreateOrgProjectBody, ProjectConfigUpdate, ShareLocalProjectBody
from lc_server.integrations.firebase_auth import FirebaseUser
from lc_server.integrations.firestore_store import FirestoreStore

router = APIRouter(tags=["projects"])


@router.get("/orgs/{org_id}/projects")
def list_org_projects(
    org_id: str,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    if not store.is_org_member(org_id, user.uid):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"orgId": org_id, "projects": store.list_org_projects(org_id)}


@router.get("/orgs/{org_id}/projects/{jira_project_key}")
def get_project_config(
    org_id: str,
    jira_project_key: str,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    if not store.is_org_member(org_id, user.uid):
        raise HTTPException(status_code=403, detail="Forbidden")
    doc = store.get_project_config(org_id, jira_project_key)
    if not doc:
        raise HTTPException(status_code=404, detail="Project config not found")
    return doc


@router.put("/orgs/{org_id}/projects/{jira_project_key}")
def put_project_config(
    org_id: str,
    jira_project_key: str,
    body: ProjectConfigUpdate,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    if not store.is_org_member(org_id, user.uid):
        raise HTTPException(status_code=403, detail="Forbidden")
    payload = body.model_dump(exclude_none=True)
    return store.save_project_config(org_id, jira_project_key, payload)


@router.patch("/orgs/{org_id}/projects/{jira_project_key}")
def patch_project_config(
    org_id: str,
    jira_project_key: str,
    body: ProjectConfigUpdate,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    return put_project_config(org_id, jira_project_key, body, user, store)


@router.post("/orgs/{org_id}/projects")
def create_org_project(
    org_id: str,
    body: CreateOrgProjectBody,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        project = store.create_org_project(org_id, body.jiraProjectKey, body.projectName, user.uid)
    except ValueError as exc:
        message = str(exc)
        status = 403 if message == "Forbidden" else 409 if "already exists" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return {"orgId": org_id, "project": project}


@router.post("/orgs/{org_id}/projects/{jira_project_key}/share-from-local")
def share_from_local_project(
    org_id: str,
    jira_project_key: str,
    body: ShareLocalProjectBody,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    key = (body.jiraProjectKey or jira_project_key).strip().upper()
    try:
        if body.mapping is not None or body.deliverySettings is not None or body.projectName:
            payload = body.model_dump(exclude_none=True)
            payload["jiraProjectKey"] = key
            project = store.save_project_config(org_id, key, payload)
        else:
            project = store.share_local_project_to_org(org_id, key, user.uid)
    except ValueError as exc:
        message = str(exc)
        status = 403 if message == "Forbidden" else 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from exc
    store.append_org_audit_event(
        org_id,
        user,
        "project.shared_from_local",
        {"jiraProjectKey": key, "projectName": project.get("projectName") or key},
    )
    return {"orgId": org_id, "project": project}


@router.post("/orgs/{org_id}/projects/share-local")
def share_local_project_legacy_path(
    org_id: str,
    body: ShareLocalProjectBody,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    key = body.jiraProjectKey.strip().upper()
    return share_from_local_project(org_id, key, body, user, store)


@router.delete("/orgs/{org_id}/projects/{jira_project_key}")
def delete_org_project(
    org_id: str,
    jira_project_key: str,
    user: FirebaseUser = Depends(require_user),
    store: FirestoreStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        store.delete_org_project(org_id, jira_project_key, user.uid)
    except ValueError as exc:
        message = str(exc)
        status = 403 if message == "Forbidden" else 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return {"orgId": org_id, "deletedProjectKey": jira_project_key.strip().upper()}
