"""Firestore persistence for LivingColor orgs, projects, and user preferences."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

from lc_server.integrations.firebase_admin import get_firebase_auth, get_firestore
from lc_server.integrations.firebase_auth import FirebaseUser

ORG_ROLES = frozenset({"admin", "member"})
INVITE_STATUSES = frozenset({"pending", "accepted", "revoked"})


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _personal_org_id(uid: str) -> str:
    return f"personal-{uid}"


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _invite_doc_id(email: str) -> str:
    normalized = _normalize_email(email)
    safe = re.sub(r"[^a-z0-9@._+-]", "_", normalized)
    return safe.replace("@", "_at_")


class FirestoreStore:
    """Server-side Firestore access (Admin SDK writes only)."""

    def _sync_user_org_membership(self, uid: str, org_id: str, *, add: bool) -> None:
        """Keep users/{uid}.organizations in sync with membership docs (VisualQ pattern)."""
        ref = get_firestore().collection("users").document(uid)
        doc = ref.get()
        data = doc.to_dict() or {} if doc.exists else {}
        orgs = [str(org) for org in (data.get("organizations") or []) if str(org).strip()]

        if add:
            if org_id not in orgs:
                orgs.append(org_id)
            ref.set({"organizations": orgs, "updatedAt": _now_iso()}, merge=True)
            return

        orgs = [org for org in orgs if org != org_id]
        patch: dict[str, Any] = {"organizations": orgs, "updatedAt": _now_iso()}
        if data.get("activeOrgId") == org_id:
            patch["activeOrgId"] = orgs[0] if orgs else _personal_org_id(uid)
        ref.set(patch, merge=True)

    def _org_summary_for_member(self, org_id: str, uid: str) -> dict[str, Any] | None:
        org_ref = get_firestore().collection("organizations").document(org_id)
        org_doc = org_ref.get()
        if not org_doc.exists:
            return None
        member_doc = org_ref.collection("members").document(uid).get()
        if not member_doc.exists:
            return None
        org_data = org_doc.to_dict() or {}
        member_data = member_doc.to_dict() or {}
        return {
            "id": org_doc.id,
            "name": org_data.get("name") or org_doc.id,
            "kind": org_data.get("kind") or "team",
            "role": member_data.get("role") or "member",
        }

    def get_user(self, uid: str) -> dict[str, Any] | None:
        doc = get_firestore().collection("users").document(uid).get()
        return doc.to_dict() if doc.exists else None

    def upsert_user(self, user: FirebaseUser) -> dict[str, Any]:
        ref = get_firestore().collection("users").document(user.uid)
        existing = ref.get()
        payload: dict[str, Any] = {
            "email": user.email,
            "displayName": user.display_name,
            "updatedAt": _now_iso(),
        }
        if not existing.exists:
            payload["createdAt"] = payload["updatedAt"]
            payload["activeOrgId"] = _personal_org_id(user.uid)
        ref.set(payload, merge=True)
        merged = {**(existing.to_dict() or {}), **payload}
        return merged

    def get_org(self, org_id: str) -> dict[str, Any] | None:
        doc = get_firestore().collection("organizations").document(org_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        return {"id": doc.id, **data}

    def ensure_personal_org(self, user: FirebaseUser) -> str:
        org_id = _personal_org_id(user.uid)
        db = get_firestore()
        org_ref = db.collection("organizations").document(org_id)
        member_ref = org_ref.collection("members").document(user.uid)

        if not org_ref.get().exists:
            org_ref.set(
                {
                    "name": user.display_name or user.email or "Personal",
                    "kind": "personal",
                    "createdAt": _now_iso(),
                    "updatedAt": _now_iso(),
                }
            )
        if not member_ref.get().exists:
            member_ref.set(
                {
                    "uid": user.uid,
                    "role": "admin",
                    "email": user.email,
                    "displayName": user.display_name,
                    "joinedAt": _now_iso(),
                }
            )
            self._sync_user_org_membership(user.uid, org_id, add=True)

        user_ref = db.collection("users").document(user.uid)
        user_doc = user_ref.get()
        active_org = (user_doc.to_dict() or {}).get("activeOrgId")
        if not active_org:
            user_ref.set({"activeOrgId": org_id, "updatedAt": _now_iso()}, merge=True)
        return org_id

    def create_team_org(self, name: str, creator: FirebaseUser) -> dict[str, Any]:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Organization name is required")

        org_id = f"team-{uuid.uuid4().hex[:12]}"
        db = get_firestore()
        org_ref = db.collection("organizations").document(org_id)
        org_ref.set(
            {
                "name": cleaned,
                "kind": "team",
                "createdBy": creator.uid,
                "createdAt": _now_iso(),
                "updatedAt": _now_iso(),
            }
        )
        org_ref.collection("members").document(creator.uid).set(
            {
                "uid": creator.uid,
                "role": "admin",
                "email": creator.email,
                "displayName": creator.display_name,
                "joinedAt": _now_iso(),
            }
        )
        self._sync_user_org_membership(creator.uid, org_id, add=True)
        return {"id": org_id, "name": cleaned, "kind": "team", "role": "admin"}

    def set_active_org(self, uid: str, org_id: str) -> dict[str, Any]:
        if not self.is_org_member(org_id, uid):
            raise ValueError("Not a member of this organization")
        ref = get_firestore().collection("users").document(uid)
        ref.set({"activeOrgId": org_id, "updatedAt": _now_iso()}, merge=True)
        profile = self.get_user(uid) or {}
        return {"activeOrgId": org_id, "profile": profile}

    def list_user_orgs(self, uid: str) -> list[dict[str, Any]]:
        profile = self.get_user(uid) or {}
        indexed_org_ids = profile.get("organizations")
        if isinstance(indexed_org_ids, list) and indexed_org_ids:
            orgs: list[dict[str, Any]] = []
            for org_id in indexed_org_ids:
                summary = self._org_summary_for_member(str(org_id), uid)
                if summary is not None:
                    orgs.append(summary)
            if orgs:
                orgs.sort(key=lambda row: (0 if row.get("kind") == "personal" else 1, row.get("name") or ""))
                return orgs
            # Stale users/{uid}.organizations index — fall through to membership scan.

        db = get_firestore()
        orgs = []
        try:
            for doc in db.collection_group("members").where("uid", "==", uid).stream():
                org_ref = doc.reference.parent.parent
                if org_ref is None:
                    continue
                summary = self._org_summary_for_member(org_ref.id, uid)
                if summary is not None:
                    orgs.append(summary)
                    self._sync_user_org_membership(uid, org_ref.id, add=True)
        except Exception as exc:
            logger.warning("Org membership scan skipped: %s", exc)
        orgs.sort(key=lambda row: (0 if row.get("kind") == "personal" else 1, row.get("name") or ""))
        return orgs

    def resolve_active_org_id(self, user: FirebaseUser) -> str:
        """Return a membership-valid active org, repairing stale profile pointers."""
        personal_org_id = _personal_org_id(user.uid)
        self.ensure_personal_org(user)
        profile = self.get_user(user.uid) or {}
        candidate = str(profile.get("activeOrgId") or personal_org_id).strip()
        if candidate and candidate != "local" and self.is_org_member(candidate, user.uid):
            return candidate
        get_firestore().collection("users").document(user.uid).set(
            {"activeOrgId": personal_org_id, "updatedAt": _now_iso()},
            merge=True,
        )
        return personal_org_id

    def list_org_members(self, org_id: str) -> list[dict[str, Any]]:
        db = get_firestore()
        members: list[dict[str, Any]] = []
        for doc in db.collection("organizations").document(org_id).collection("members").stream():
            data = doc.to_dict() or {}
            members.append(
                {
                    "uid": doc.id,
                    "email": data.get("email") or "",
                    "displayName": data.get("displayName") or data.get("email") or doc.id,
                    "role": data.get("role") or "member",
                    "joinedAt": data.get("joinedAt"),
                }
            )
        members.sort(key=lambda row: (0 if row.get("role") == "admin" else 1, row.get("displayName") or ""))
        return members

    def list_org_projects(self, org_id: str) -> list[dict[str, Any]]:
        db = get_firestore()
        projects: list[dict[str, Any]] = []
        for doc in db.collection("organizations").document(org_id).collection("projects").stream():
            data = doc.to_dict() or {}
            projects.append(
                {
                    "jiraProjectKey": data.get("jiraProjectKey") or doc.id,
                    "projectName": data.get("projectName") or doc.id,
                    "updatedAt": data.get("updatedAt"),
                }
            )
        projects.sort(key=lambda row: row.get("jiraProjectKey") or "")
        return projects

    def share_local_project_to_org(
        self,
        org_id: str,
        jira_project_key: str,
        actor_uid: str,
    ) -> dict[str, Any]:
        from lc_server.integrations.local_project_share import build_local_project_share_payload

        if not self.is_org_member(org_id, actor_uid):
            raise ValueError("Forbidden")

        payload = build_local_project_share_payload(jira_project_key)
        key = str(payload["jiraProjectKey"])
        name = str(payload["projectName"])
        ref = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("projects")
            .document(key)
        )
        if not ref.get().exists:
            self.create_org_project(org_id, key, name, actor_uid)
        saved = self.save_project_config(
            org_id,
            key,
            {
                "projectName": name,
                "mapping": payload.get("mapping"),
                "deliverySettings": payload.get("deliverySettings"),
                "sharedFromLocal": True,
            },
        )
        return saved

    def create_org_project(
        self,
        org_id: str,
        jira_project_key: str,
        project_name: str,
        actor_uid: str,
    ) -> dict[str, Any]:
        if not self.is_org_member(org_id, actor_uid):
            raise ValueError("Forbidden")
        key = jira_project_key.strip().upper()
        name = project_name.strip()
        if not key or not re.fullmatch(r"[A-Z][A-Z0-9]{1,19}", key):
            raise ValueError("Invalid Jira project key")
        if not name:
            raise ValueError("Project name is required")
        ref = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("projects")
            .document(key)
        )
        if ref.get().exists:
            raise ValueError("Project already exists")
        payload = {
            "jiraProjectKey": key,
            "projectName": name,
            "createdAt": _now_iso(),
            "updatedAt": _now_iso(),
        }
        ref.set(payload)
        get_firestore().collection("organizations").document(org_id).set(
            {"updatedAt": _now_iso()}, merge=True
        )
        return payload

    def delete_org_project(self, org_id: str, jira_project_key: str, actor_uid: str) -> None:
        if not self.is_org_member(org_id, actor_uid):
            raise ValueError("Forbidden")
        key = jira_project_key.strip().upper()
        ref = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("projects")
            .document(key)
        )
        if not ref.get().exists:
            raise ValueError("Project not found")
        ref.delete()
        get_firestore().collection("organizations").document(org_id).set(
            {"updatedAt": _now_iso()}, merge=True
        )

    def _require_team_org(self, org_id: str) -> dict[str, Any]:
        org = self.get_org(org_id)
        if org is None:
            raise ValueError("Organization not found")
        if org.get("kind") == "personal":
            raise ValueError("Personal workspaces cannot be shared")
        return org

    def resolve_user_by_email(self, email: str) -> tuple[str, str, str] | None:
        normalized = _normalize_email(email)
        if not normalized:
            return None
        try:
            record = get_firebase_auth().get_user_by_email(normalized)
        except Exception:
            return None
        return (
            str(record.uid),
            str(record.email or normalized),
            str(record.display_name or record.email or normalized),
        )

    def _add_member_record(
        self,
        org_id: str,
        uid: str,
        email: str,
        display_name: str,
        role: str,
    ) -> dict[str, Any]:
        if role not in ORG_ROLES:
            raise ValueError("Invalid role")
        ref = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("members")
            .document(uid)
        )
        payload = {
            "uid": uid,
            "role": role,
            "email": email,
            "displayName": display_name,
            "joinedAt": _now_iso(),
        }
        ref.set(payload, merge=True)
        get_firestore().collection("organizations").document(org_id).set(
            {"updatedAt": _now_iso()}, merge=True
        )
        self._sync_user_org_membership(uid, org_id, add=True)
        return {"uid": uid, **payload}

    def invite_org_member(
        self,
        org_id: str,
        email: str,
        role: str,
        inviter_uid: str,
    ) -> dict[str, Any]:
        self._require_team_org(org_id)
        if role not in ORG_ROLES:
            raise ValueError("Invalid role")
        if not self.is_org_admin(org_id, inviter_uid):
            raise ValueError("Admin role required")

        normalized = _normalize_email(email)
        if not normalized:
            raise ValueError("Email is required")

        resolved = self.resolve_user_by_email(normalized)
        if resolved is not None:
            uid, resolved_email, display_name = resolved
            if self.is_org_member(org_id, uid):
                raise ValueError("User is already a member")
            member = self._add_member_record(org_id, uid, resolved_email, display_name, role)
            return {"status": "added", "member": member}

        invite_ref = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("invites")
            .document(_invite_doc_id(normalized))
        )
        existing = invite_ref.get()
        if existing.exists and (existing.to_dict() or {}).get("status") == "pending":
            raise ValueError("Invite already pending for this email")

        invite_payload = {
            "email": normalized,
            "role": role,
            "status": "pending",
            "invitedBy": inviter_uid,
            "invitedAt": _now_iso(),
        }
        invite_ref.set(invite_payload, merge=True)
        get_firestore().collection("organizations").document(org_id).set(
            {"updatedAt": _now_iso()}, merge=True
        )
        return {"status": "invited", "invite": invite_payload}

    def list_org_invites(self, org_id: str) -> list[dict[str, Any]]:
        self._require_team_org(org_id)
        invites: list[dict[str, Any]] = []
        for doc in (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("invites")
            .stream()
        ):
            data = doc.to_dict() or {}
            if str(data.get("status") or "") != "pending":
                continue
            invites.append(
                {
                    "id": doc.id,
                    "email": data.get("email") or "",
                    "role": data.get("role") or "member",
                    "status": data.get("status") or "pending",
                    "invitedAt": data.get("invitedAt"),
                    "invitedBy": data.get("invitedBy"),
                }
            )
        invites.sort(key=lambda row: row.get("invitedAt") or "")
        return invites

    def revoke_org_invite(self, org_id: str, invite_id: str, actor_uid: str) -> None:
        self._require_team_org(org_id)
        if not self.is_org_admin(org_id, actor_uid):
            raise ValueError("Admin role required")
        invite_ref = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("invites")
            .document(invite_id)
        )
        doc = invite_ref.get()
        if not doc.exists:
            raise ValueError("Invite not found")
        if str((doc.to_dict() or {}).get("status") or "") != "pending":
            raise ValueError("Invite is not pending")
        invite_ref.set({"status": "revoked", "revokedAt": _now_iso()}, merge=True)
        get_firestore().collection("organizations").document(org_id).set(
            {"updatedAt": _now_iso()}, merge=True
        )

    def accept_pending_invites(self, user: FirebaseUser) -> list[str]:
        if not user.email:
            return []
        db = get_firestore()
        joined: list[str] = []
        normalized = _normalize_email(user.email)
        try:
            pending_invites = (
                db.collection_group("invites")
                .where("email", "==", normalized)
                .where("status", "==", "pending")
                .stream()
            )
            for doc in pending_invites:
                org_ref = doc.reference.parent.parent
                if org_ref is None:
                    continue
                org_id = org_ref.id
                invite = doc.to_dict() or {}
                role = str(invite.get("role") or "member")
                if role not in ORG_ROLES:
                    role = "member"
                if not self.is_org_member(org_id, user.uid):
                    self._add_member_record(
                        org_id,
                        user.uid,
                        user.email,
                        user.display_name,
                        role,
                    )
                doc.reference.set({"status": "accepted", "acceptedAt": _now_iso()}, merge=True)
                joined.append(org_id)
        except Exception as exc:
            # Composite index may not be deployed yet; bootstrap must still succeed.
            logger.warning("Pending invite lookup skipped: %s", exc)
        return joined

    def remove_org_member(self, org_id: str, member_uid: str, actor_uid: str) -> None:
        self._require_team_org(org_id)
        if not self.is_org_admin(org_id, actor_uid):
            raise ValueError("Admin role required")
        if member_uid == actor_uid:
            raise ValueError("Admins cannot remove themselves")
        if not self.is_org_member(org_id, member_uid):
            raise ValueError("Member not found")

        members = self.list_org_members(org_id)
        admins = [row for row in members if row.get("role") == "admin"]
        target = next((row for row in members if row.get("uid") == member_uid), None)
        if target and target.get("role") == "admin" and len(admins) <= 1:
            raise ValueError("Cannot remove the last admin")

        (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("members")
            .document(member_uid)
            .delete()
        )
        self._sync_user_org_membership(member_uid, org_id, add=False)
        get_firestore().collection("organizations").document(org_id).set(
            {"updatedAt": _now_iso()}, merge=True
        )

    def is_org_member(self, org_id: str, uid: str) -> bool:
        doc = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("members")
            .document(uid)
            .get()
        )
        return doc.exists

    def is_org_admin(self, org_id: str, uid: str) -> bool:
        doc = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("members")
            .document(uid)
            .get()
        )
        if not doc.exists:
            return False
        return str((doc.to_dict() or {}).get("role") or "") == "admin"

    def get_project_config(self, org_id: str, jira_project_key: str) -> dict[str, Any] | None:
        doc = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("projects")
            .document(jira_project_key.upper())
            .get()
        )
        return doc.to_dict() if doc.exists else None

    def save_project_config(
        self,
        org_id: str,
        jira_project_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        key = jira_project_key.upper()
        ref = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("projects")
            .document(key)
        )
        existing = ref.get()
        merged = {
            **(existing.to_dict() or {}),
            **payload,
            "jiraProjectKey": key,
            "updatedAt": _now_iso(),
        }
        if not existing.exists:
            merged["createdAt"] = merged["updatedAt"]
        ref.set(merged, merge=True)
        return merged

    def get_user_preferences(self, org_id: str, uid: str) -> dict[str, Any] | None:
        doc = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("userPreferences")
            .document(uid)
            .get()
        )
        return doc.to_dict() if doc.exists else None

    def save_user_preferences(
        self,
        org_id: str,
        uid: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        ref = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("userPreferences")
            .document(uid)
        )
        existing = ref.get()
        merged = {**(existing.to_dict() or {}), **payload, "updatedAt": _now_iso()}
        if not existing.exists:
            merged["createdAt"] = merged["updatedAt"]
        ref.set(merged, merge=True)
        return merged

    def get_work_order_lock(self, org_id: str, wo_id: str) -> dict[str, Any] | None:
        doc = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("locks")
            .document(wo_id)
            .get()
        )
        return doc.to_dict() if doc.exists else None

    def acquire_work_order_lock(
        self,
        org_id: str,
        wo_id: str,
        user: FirebaseUser,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_org_member(org_id, user.uid):
            raise ValueError("Forbidden")
        key = wo_id.strip()
        if not key:
            raise ValueError("Work order id is required")
        ref = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("locks")
            .document(key)
        )
        existing = ref.get()
        if existing.exists:
            holder_uid = str((existing.to_dict() or {}).get("holderUid") or "")
            if holder_uid and holder_uid != user.uid:
                raise ValueError("Lock held by another member")
        payload = {
            "holderUid": user.uid,
            "holderEmail": user.email,
            "acquiredAt": _now_iso(),
            "sessionId": (session_id or f"{user.uid}-default").strip(),
        }
        ref.set(payload, merge=True)
        return {"orgId": org_id, "workOrderId": key, "lock": payload}

    def release_work_order_lock(self, org_id: str, wo_id: str, user: FirebaseUser) -> dict[str, Any]:
        if not self.is_org_member(org_id, user.uid):
            raise ValueError("Forbidden")
        key = wo_id.strip()
        ref = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("locks")
            .document(key)
        )
        doc = ref.get()
        if not doc.exists:
            return {"orgId": org_id, "workOrderId": key, "released": True}
        holder_uid = str((doc.to_dict() or {}).get("holderUid") or "")
        if holder_uid and holder_uid != user.uid:
            raise ValueError("Lock held by another member")
        ref.delete()
        return {"orgId": org_id, "workOrderId": key, "released": True}

    def get_work_order_snapshot(self, org_id: str, wo_id: str) -> dict[str, Any] | None:
        key = wo_id.strip()
        if not key:
            return None
        doc = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("workOrders")
            .document(key)
            .get()
        )
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        data["id"] = doc.id
        return data

    def _upsert_work_order_snapshot(
        self,
        org_id: str,
        wo_id: str,
        snapshot: dict[str, Any],
        updated_at: str,
    ) -> None:
        key = wo_id.strip()
        patch = {
            key_name: value
            for key_name, value in snapshot.items()
            if key_name not in {"id"} and value is not None
        }
        patch["updatedAt"] = str(patch.get("updatedAt") or updated_at)
        if "createdAt" not in patch:
            patch["createdAt"] = updated_at
        (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("workOrders")
            .document(key)
            .set(patch, merge=True)
        )

    def append_org_audit_event(
        self,
        org_id: str,
        user: FirebaseUser,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.is_org_member(org_id, user.uid):
            raise ValueError("Forbidden")
        created_at = _now_iso()
        event_ref = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("events")
            .document()
        )
        event_payload = {
            "eventType": event_type,
            "actorUid": user.uid,
            "actorEmail": user.email,
            "payload": payload,
            "createdAt": created_at,
        }
        event_ref.set(event_payload)
        return {"orgId": org_id, "eventId": event_ref.id, "event": event_payload}

    def append_org_event(
        self,
        org_id: str,
        user: FirebaseUser,
        wo_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.is_org_member(org_id, user.uid):
            raise ValueError("Forbidden")
        key = wo_id.strip()
        if not key:
            raise ValueError("Work order id is required")
        lock = self.get_work_order_lock(org_id, key) or {}
        holder_uid = str(lock.get("holderUid") or "")
        if holder_uid and holder_uid != user.uid:
            raise ValueError("Lock held by another member")
        created_at = _now_iso()
        event_ref = (
            get_firestore()
            .collection("organizations")
            .document(org_id)
            .collection("events")
            .document()
        )
        event_payload = {
            "woId": key,
            "eventType": event_type,
            "actorUid": user.uid,
            "actorEmail": user.email,
            "payload": payload,
            "createdAt": created_at,
        }
        event_ref.set(event_payload)
        work_order_patch = payload.get("workOrder")
        if isinstance(work_order_patch, dict):
            self._upsert_work_order_snapshot(org_id, key, work_order_patch, created_at)
        return {"orgId": org_id, "eventId": event_ref.id, "event": event_payload}

    def reconcile_pending_events(
        self,
        org_id: str,
        user: FirebaseUser,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.is_org_member(org_id, user.uid):
            raise ValueError("Forbidden")
        accepted: list[int | str] = []
        conflicts: list[dict[str, Any]] = []
        for item in events:
            local_id = item.get("id")
            wo_id = str(item.get("woId") or "").strip()
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            if not wo_id:
                continue
            client_version = str(payload.get("updatedAt") or payload.get("clientUpdatedAt") or "")
            server = self.get_work_order_snapshot(org_id, wo_id)
            server_version = str((server or {}).get("updatedAt") or "")
            if server_version and client_version and server_version > client_version:
                conflicts.append(
                    {
                        "woId": wo_id,
                        "serverVersion": server_version,
                        "clientVersion": client_version,
                        "localEventId": local_id,
                    }
                )
                continue
            event_type = str(payload.get("type") or payload.get("eventType") or "state_change")
            self.append_org_event(org_id, user, wo_id, event_type, payload)
            if local_id is not None:
                accepted.append(local_id)
        return {"orgId": org_id, "accepted": accepted, "conflicts": conflicts}

    def bootstrap_user(self, user: FirebaseUser) -> dict[str, Any]:
        self.upsert_user(user)
        self.ensure_personal_org(user)
        self.accept_pending_invites(user)
        active_org_id = self.resolve_active_org_id(user)
        orgs = self.list_user_orgs(user.uid)
        return {
            "user": {
                "uid": user.uid,
                "email": user.email,
                "displayName": user.display_name,
                "activeOrgId": active_org_id,
            },
            "organizations": orgs,
        }
