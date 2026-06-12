"""Shared FastAPI dependencies for the LivingColor cloud API."""

from __future__ import annotations

from fastapi import Request

from lc_server.integrations.firebase_auth import FirebaseUser
from lc_server.integrations.firestore_store import FirestoreStore


def get_store() -> FirestoreStore:
    return FirestoreStore()


def resolve_active_org_id(request: Request, user: FirebaseUser, store: FirestoreStore) -> str:
    header_org = (
        (request.headers.get("x-lc-org-id") or request.headers.get("x-org-id") or "").strip()
    )
    if header_org and header_org != "local" and store.is_org_member(header_org, user.uid):
        return header_org
    return store.resolve_active_org_id(user)
