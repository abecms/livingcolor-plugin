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
