"""Persistence for internal Merge Request Drafts."""

from __future__ import annotations

from delivery_runtime.mr_drafts.models import MergeRequestDraft
from delivery_runtime.persistence.db import connect, json_dumps, json_loads, next_public_id, utc_now_iso


def save_mr_draft(draft: MergeRequestDraft) -> MergeRequestDraft:
    now = utc_now_iso()
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM merge_request_drafts WHERE id = ?",
            (draft.id,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE merge_request_drafts
                SET title = ?,
                    description = ?,
                    ticket_summary = ?,
                    implementation_summary = ?,
                    files_modified_json = ?,
                    risks_json = ?,
                    reviewers_json = ?,
                    qa_checklist_json = ?,
                    decision_trace_json = ?,
                    status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    draft.title,
                    draft.description,
                    draft.ticket_summary,
                    draft.implementation_summary,
                    json_dumps(draft.files_modified),
                    json_dumps(draft.risks),
                    json_dumps(draft.reviewers),
                    json_dumps(draft.qa_checklist),
                    json_dumps(draft.decision_trace),
                    draft.status,
                    now,
                    draft.id,
                ),
            )
            return load_mr_draft(draft.id) or draft

        draft_id = draft.id or next_public_id(conn, "MRD")
        created_at = draft.created_at or now
        conn.execute(
            """
            INSERT INTO merge_request_drafts (
                id, work_order_id, title, description, ticket_summary,
                implementation_summary, files_modified_json, risks_json,
                reviewers_json, qa_checklist_json, decision_trace_json, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft_id,
                draft.work_order_id,
                draft.title,
                draft.description,
                draft.ticket_summary,
                draft.implementation_summary,
                json_dumps(draft.files_modified),
                json_dumps(draft.risks),
                json_dumps(draft.reviewers),
                json_dumps(draft.qa_checklist),
                json_dumps(draft.decision_trace),
                draft.status,
                created_at,
                now,
            ),
        )
    return load_mr_draft(draft_id) or draft


def load_mr_draft(draft_id: str) -> MergeRequestDraft | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM merge_request_drafts WHERE id = ?",
            (draft_id,),
        ).fetchone()
    if not row:
        return None
    return _row_to_draft(row)


def load_mr_draft_for_work_order(work_order_id: str) -> MergeRequestDraft | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM merge_request_drafts
            WHERE work_order_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (work_order_id,),
        ).fetchone()
    if not row:
        return None
    return _row_to_draft(row)


def set_mr_draft_publication(draft_id: str, *, mr_url: str, mr_iid: int) -> MergeRequestDraft | None:
    """Record the published GitLab MR location on the draft."""
    now = utc_now_iso()
    with connect() as conn:
        conn.execute(
            """
            UPDATE merge_request_drafts
            SET mr_url = ?, mr_iid = ?, updated_at = ?
            WHERE id = ?
            """,
            (mr_url, mr_iid, now, draft_id),
        )
    return load_mr_draft(draft_id)


def update_mr_draft_status(draft_id: str, status: str) -> MergeRequestDraft | None:
    now = utc_now_iso()
    with connect() as conn:
        conn.execute(
            """
            UPDATE merge_request_drafts
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, now, draft_id),
        )
    return load_mr_draft(draft_id)


def _row_to_draft(row) -> MergeRequestDraft:
    return MergeRequestDraft(
        id=str(row["id"]),
        work_order_id=str(row["work_order_id"]),
        title=str(row["title"]),
        description=str(row["description"]),
        ticket_summary=str(row["ticket_summary"]),
        implementation_summary=str(row["implementation_summary"]),
        files_modified=json_loads(row["files_modified_json"], []),
        risks=json_loads(row["risks_json"], []),
        reviewers=json_loads(row["reviewers_json"], []),
        qa_checklist=json_loads(row["qa_checklist_json"], {}),
        decision_trace=json_loads(row["decision_trace_json"], {})
        if "decision_trace_json" in row.keys()
        else {},
        mr_url=str(row["mr_url"]) if "mr_url" in row.keys() else "",
        mr_iid=int(row["mr_iid"]) if "mr_iid" in row.keys() and row["mr_iid"] is not None else None,
        status=str(row["status"]),  # type: ignore[arg-type]
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
