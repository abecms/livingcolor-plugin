"""MR draft publication metadata persistence."""

from delivery_runtime.mr_drafts.models import MergeRequestDraft
from delivery_runtime.mr_drafts.store import (
    load_mr_draft,
    save_mr_draft,
    set_mr_draft_publication,
)
from delivery_runtime.persistence.db import connect, init_db, utc_now_iso


def _seed_work_order(conn, work_order_id: str = "WO-1") -> None:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO work_orders (
            id, jira_key, readiness_id, title, status, current_stage, created_at, updated_at
        ) VALUES (?, 'TEST-1', NULL, 'Test work order', 'running', 'mr_draft', ?, ?)
        """,
        (work_order_id, now, now),
    )


def _make_draft():
    return save_mr_draft(
        MergeRequestDraft(
            id="",
            work_order_id="WO-1",
            title="t",
            description="d",
            ticket_summary="s",
            implementation_summary="i",
        )
    )


def test_set_publication_metadata(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        _seed_work_order(conn)

    draft = _make_draft()
    updated = set_mr_draft_publication(
        draft.id, mr_url="https://gitlab.example.com/g/p/-/merge_requests/42", mr_iid=42
    )
    assert updated.mr_url == "https://gitlab.example.com/g/p/-/merge_requests/42"
    assert updated.mr_iid == 42

    reloaded = load_mr_draft(draft.id)
    assert reloaded.mr_iid == 42
    assert reloaded.to_dict()["mrUrl"] == "https://gitlab.example.com/g/p/-/merge_requests/42"


def test_publication_fields_default_empty(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        _seed_work_order(conn)

    draft = _make_draft()
    assert draft.mr_url == ""
    assert draft.mr_iid is None


def test_mr_draft_publication_stores_provider_neutral_fields(livingcolor_home):
    from delivery_runtime.mr_drafts.models import MergeRequestDraft
    from delivery_runtime.mr_drafts.store import load_mr_draft, save_mr_draft, set_mr_draft_publication
    from delivery_runtime.persistence.db import connect, init_db, utc_now_iso

    init_db()
    now = utc_now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO work_orders (
                id, jira_key, readiness_id, title, status, current_stage, created_at, updated_at
            ) VALUES ('WO-GH-1', 'GH-1', NULL, 'GH-1', 'running', 'mr_draft', ?, ?)
            """,
            (now, now),
        )
    draft = save_mr_draft(
        MergeRequestDraft(
            id="MRD-GH-1",
            work_order_id="WO-GH-1",
            title="GH-1",
            description="Body",
            ticket_summary="",
            implementation_summary="",
            files_modified=[],
            risks=[],
            reviewers=[],
            qa_checklist={},
            decision_trace={},
            status="approved",
            created_at=now,
            updated_at=now,
        )
    )

    set_mr_draft_publication(
        draft.id,
        review_request_url="https://github.com/org/app/pull/42",
        review_request_number=42,
        review_request_provider="github",
    )

    loaded = load_mr_draft(draft.id)
    assert loaded.review_request_url == "https://github.com/org/app/pull/42"
    assert loaded.review_request_number == 42
    assert loaded.review_request_provider == "github"
    assert loaded.mr_url == "https://github.com/org/app/pull/42"
    assert loaded.mr_iid == 42
