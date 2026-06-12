"""Tests for Firestore org collaboration helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lc_server.integrations import firestore_store


@dataclass
class FakeUser:
    uid: str
    email: str
    display_name: str
    email_verified: bool = True


def test_invite_doc_id_normalizes_email():
    assert firestore_store._invite_doc_id("Alice@Example.com") == "alice_at_example.com"


def test_create_team_org_requires_name(monkeypatch):
    store = firestore_store.FirestoreStore()

    class FakeDb:
        def collection(self, *_args, **_kwargs):
            raise AssertionError("should not write when name is empty")

    monkeypatch.setattr(firestore_store, "get_firestore", lambda: FakeDb())
    with pytest.raises(ValueError, match="name is required"):
        store.create_team_org("   ", FakeUser("u1", "a@example.com", "Alice"))


def test_require_team_org_rejects_personal(monkeypatch):
    store = firestore_store.FirestoreStore()
    monkeypatch.setattr(store, "get_org", lambda _org_id: {"id": "personal-u1", "kind": "personal"})
    with pytest.raises(ValueError, match="cannot be shared"):
        store._require_team_org("personal-u1")


def test_invite_existing_user_adds_member(monkeypatch):
    store = firestore_store.FirestoreStore()
    writes: list[tuple[str, dict]] = []

    class FakeMemberRef:
        def set(self, payload, merge=False):
            writes.append(("member", payload))

    class FakeOrgRef:
        id = "team-abc"

        def set(self, payload, merge=False):
            writes.append(("org", payload))

        def collection(self, name):
            assert name == "members"
            return self

        def document(self, uid):
            assert uid == "u2"
            return FakeMemberRef()

    class FakeDb:
        def collection(self, name):
            assert name == "organizations"
            return self

        def document(self, org_id):
            assert org_id == "team-abc"
            return FakeOrgRef()

    monkeypatch.setattr(firestore_store, "get_firestore", lambda: FakeDb())
    monkeypatch.setattr(store, "_require_team_org", lambda _org_id: {"kind": "team"})
    monkeypatch.setattr(store, "is_org_admin", lambda *_args: True)
    monkeypatch.setattr(store, "is_org_member", lambda *_args: False)
    monkeypatch.setattr(store, "_sync_user_org_membership", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        store,
        "resolve_user_by_email",
        lambda _email: ("u2", "bob@example.com", "Bob"),
    )

    result = store.invite_org_member("team-abc", "bob@example.com", "member", "u1")
    assert result["status"] == "added"
    assert result["member"]["uid"] == "u2"
    assert any(kind == "member" for kind, _ in writes)


def test_accept_pending_invites_skips_when_index_missing(monkeypatch):
    store = firestore_store.FirestoreStore()

    class FakeQuery:
        def where(self, *_args, **_kwargs):
            return self

        def stream(self):
            raise RuntimeError("FailedPrecondition: index missing")

    class FakeDb:
        def collection_group(self, _name):
            return FakeQuery()

    monkeypatch.setattr(firestore_store, "get_firestore", lambda: FakeDb())
    joined = store.accept_pending_invites(FakeUser("u1", "alice@example.com", "Alice"))
    assert joined == []


def test_create_org_project_requires_valid_key(monkeypatch):
    store = firestore_store.FirestoreStore()
    monkeypatch.setattr(store, "is_org_member", lambda *_args: True)

    class FakeDb:
        def collection(self, *_args, **_kwargs):
            raise AssertionError("should not write when key is invalid")

    monkeypatch.setattr(firestore_store, "get_firestore", lambda: FakeDb())
    with pytest.raises(ValueError, match="Invalid Jira project key"):
        store.create_org_project("org-1", "bad key", "Name", "u1")


def test_sync_user_org_membership_adds_org_id(monkeypatch):
    store = firestore_store.FirestoreStore()
    patches: list[dict] = []

    class FakeUserRef:
        def get(self):
            class Doc:
                exists = True

                def to_dict(self):
                    return {"organizations": ["personal-u1"]}

            return Doc()

        def set(self, payload, merge=False):
            patches.append(payload)

    class FakeDb:
        def collection(self, name):
            assert name == "users"
            return self

        def document(self, uid):
            assert uid == "u1"
            return FakeUserRef()

    monkeypatch.setattr(firestore_store, "get_firestore", lambda: FakeDb())
    store._sync_user_org_membership("u1", "team-abc", add=True)
    assert patches[-1]["organizations"] == ["personal-u1", "team-abc"]


def test_sync_user_org_membership_clears_active_org_when_removed(monkeypatch):
    store = firestore_store.FirestoreStore()
    patches: list[dict] = []

    class FakeUserRef:
        def get(self):
            class Doc:
                exists = True

                def to_dict(self):
                    return {
                        "organizations": ["personal-u1", "team-abc"],
                        "activeOrgId": "team-abc",
                    }

            return Doc()

        def set(self, payload, merge=False):
            patches.append(payload)

    class FakeDb:
        def collection(self, name):
            assert name == "users"
            return self

        def document(self, uid):
            assert uid == "u1"
            return FakeUserRef()

    monkeypatch.setattr(firestore_store, "get_firestore", lambda: FakeDb())
    store._sync_user_org_membership("u1", "team-abc", add=False)
    assert patches[-1]["organizations"] == ["personal-u1"]
    assert patches[-1]["activeOrgId"] == "personal-u1"


def test_revoke_org_invite_requires_pending_status(monkeypatch):
    store = firestore_store.FirestoreStore()
    monkeypatch.setattr(store, "_require_team_org", lambda _org_id: {"kind": "team"})
    monkeypatch.setattr(store, "is_org_admin", lambda *_args: True)

    class FakeInviteRef:
        def get(self):
            class Doc:
                exists = True

                def to_dict(self):
                    return {"status": "accepted"}

            return Doc()

        def set(self, *_args, **_kwargs):
            raise AssertionError("should not write when invite is not pending")

    class FakeOrgRef:
        def collection(self, name):
            assert name == "invites"
            return self

        def document(self, invite_id):
            assert invite_id == "alice_at_example.com"
            return FakeInviteRef()

        def set(self, *_args, **_kwargs):
            pass

    class FakeDb:
        def collection(self, name):
            assert name == "organizations"
            return self

        def document(self, org_id):
            assert org_id == "team-abc"
            return FakeOrgRef()

    monkeypatch.setattr(firestore_store, "get_firestore", lambda: FakeDb())
    with pytest.raises(ValueError, match="not pending"):
        store.revoke_org_invite("team-abc", "alice_at_example.com", "u1")
