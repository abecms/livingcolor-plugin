"""Merge Request Draft workflow service (Phase 4A)."""

from __future__ import annotations

from typing import Any

from delivery_runtime.events.store import EventStore
from delivery_runtime.gates.constants import (
    CODE_REVIEW_GATE_TYPE,
    GATE1_TYPE,
    MR_REVIEW_GATE_TYPE,
)
from delivery_runtime.mr_drafts.generator import generate_mr_draft_content
from delivery_runtime.mr_drafts.models import MergeRequestDraft
from delivery_runtime.mr_drafts.store import (
    load_mr_draft,
    load_mr_draft_for_work_order,
    save_mr_draft,
    update_mr_draft_status,
)
from delivery_runtime.persistence.db import connect, json_dumps, json_loads, next_public_id, utc_now_iso
from delivery_runtime.shadow.mode import is_shadow_mode


class MrDraftService:
    def __init__(
        self,
        events: EventStore | None = None,
        *,
        orchestrator: Any | None = None,
    ) -> None:
        self.events = events or EventStore()
        self.orchestrator = orchestrator

    def bind_orchestrator(self, orchestrator: Any) -> None:
        self.orchestrator = orchestrator

    def get_draft(self, draft_id: str) -> MergeRequestDraft | None:
        return load_mr_draft(draft_id)

    def create_draft_after_code_review(
        self,
        work_order_id: str,
        *,
        code_review_gate_id: str,
    ) -> MergeRequestDraft:
        context = _load_draft_context(work_order_id, code_review_gate_id)
        from delivery_runtime.automation.config import load_delivery_automation_config

        content = generate_mr_draft_content(
            **context,
            communication_language=load_delivery_automation_config().communication_language,
        )
        with connect() as conn:
            draft_id = next_public_id(conn, "MRD")
        now = utc_now_iso()
        draft = save_mr_draft(
            MergeRequestDraft(
                id=draft_id,
                work_order_id=work_order_id,
                title=content["title"],
                description=content["description"],
                ticket_summary=content["ticketSummary"],
                implementation_summary=content["implementationSummary"],
                files_modified=content["filesModified"],
                risks=content["risks"],
                reviewers=content["reviewers"],
                qa_checklist=content["qaChecklist"],
                decision_trace=content["decisionTrace"],
                status="awaiting_review",
                created_at=now,
                updated_at=now,
            )
        )
        if is_shadow_mode():
            self._complete_synthetic_nodes(work_order_id, draft)
        else:
            self._attach_draft_to_publication_node(work_order_id, draft)
        gate_id = self._open_mr_review_gate(work_order_id, draft, context["code_review_payload"])
        self.events.append(
            event_type="MR_DRAFT_CREATED",
            work_order_id=work_order_id,
            actor="system",
            payload={"draftId": draft.id, "gateId": gate_id},
        )
        return draft

    def approve_draft(self, draft_id: str, *, approved_by: str = "human") -> MergeRequestDraft:
        draft = self._require_reviewable_draft(draft_id)
        gate = _pending_mr_gate_for_draft(draft.work_order_id, draft_id)
        if not gate:
            raise ValueError("No pending MR review gate for this draft")

        now = utc_now_iso()
        next_stage = "awaiting_next_phase" if is_shadow_mode() else "mr_publication"
        with connect() as conn:
            conn.execute(
                """
                UPDATE gates
                SET status = 'approved', approved_at = ?, approved_by = ?
                WHERE id = ?
                """,
                (now, approved_by, gate["id"]),
            )
            conn.execute(
                """
                UPDATE work_orders
                SET status = 'running', current_stage = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_stage, now, draft.work_order_id),
            )

        updated = update_mr_draft_status(draft_id, "approved")
        if not updated:
            raise RuntimeError("Failed to update MR draft status")

        merge_requeue = self._maybe_requeue_merge_conflicts(draft.work_order_id)
        if merge_requeue:
            self.events.append(
                event_type="MERGE_CONFLICT_REQUEUE",
                work_order_id=draft.work_order_id,
                actor=approved_by,
                payload=merge_requeue,
            )
            if self.orchestrator:
                self.orchestrator.tick(draft.work_order_id)
            return updated

        self.events.append(
            event_type="MR_DRAFT_APPROVED",
            work_order_id=draft.work_order_id,
            actor=approved_by,
            payload={"draftId": draft_id, "gateId": gate["id"]},
        )
        self.events.append(
            event_type="GATE_APPROVED",
            work_order_id=draft.work_order_id,
            actor=approved_by,
            payload={"gateId": gate["id"], "gateType": MR_REVIEW_GATE_TYPE},
        )
        if self.orchestrator and not is_shadow_mode():
            from delivery_runtime.orchestration.background import schedule_orchestrator_tick

            schedule_orchestrator_tick(self.orchestrator, draft.work_order_id)
        return updated

    def reject_draft(
        self,
        draft_id: str,
        *,
        feedback: str,
        rejected_by: str = "human",
    ) -> MergeRequestDraft:
        feedback = feedback.strip()
        if not feedback:
            raise ValueError("Rejection feedback is required")

        draft = self._require_reviewable_draft(draft_id)
        gate = _pending_mr_gate_for_draft(draft.work_order_id, draft_id)
        if not gate:
            raise ValueError("No pending MR review gate for this draft")

        now = utc_now_iso()
        with connect() as conn:
            conn.execute(
                """
                UPDATE gates
                SET status = 'rejected', rejection_feedback = ?, approved_by = ?
                WHERE id = ?
                """,
                (feedback, rejected_by, gate["id"]),
            )
            conn.execute(
                """
                UPDATE work_orders
                SET status = 'running', current_stage = 'mr_draft', updated_at = ?
                WHERE id = ?
                """,
                (now, draft.work_order_id),
            )

        updated = update_mr_draft_status(draft_id, "rejected")
        if not updated:
            raise RuntimeError("Failed to update MR draft status")
        self.events.append(
            event_type="MR_DRAFT_REJECTED",
            work_order_id=draft.work_order_id,
            actor=rejected_by,
            payload={"draftId": draft_id, "gateId": gate["id"], "feedback": feedback},
        )
        self.events.append(
            event_type="GATE_REJECTED",
            work_order_id=draft.work_order_id,
            actor=rejected_by,
            payload={"gateId": gate["id"], "gateType": MR_REVIEW_GATE_TYPE, "feedback": feedback},
        )
        return updated

    @staticmethod
    def _require_reviewable_draft(draft_id: str) -> MergeRequestDraft:
        draft = load_mr_draft(draft_id)
        if not draft:
            raise LookupError("MR draft not found")
        if draft.status not in {"awaiting_review", "draft"}:
            raise ValueError("Only awaiting_review drafts can be approved or rejected")
        return draft

    def _attach_draft_to_publication_node(self, work_order_id: str, draft: MergeRequestDraft) -> None:
        """Stamp the pending mr_creation node with the draft id for the publisher run."""
        with connect() as conn:
            row = conn.execute(
                """
                SELECT id, payload_json FROM graph_nodes
                WHERE work_order_id = ? AND node_type = 'mr_creation'
                """,
                (work_order_id,),
            ).fetchone()
            if not row:
                return
            merged = {**json_loads(row["payload_json"], {}), "draftId": draft.id}
            conn.execute(
                "UPDATE graph_nodes SET payload_json = ? WHERE id = ?",
                (json_dumps(merged), row["id"]),
            )

    def _complete_synthetic_nodes(self, work_order_id: str, draft: MergeRequestDraft) -> None:
        now = utc_now_iso()
        with connect() as conn:
            for node_type, payload in (
                ("mr_creation", {"draftId": draft.id, "source": "synthetic"}),
            ):
                row = conn.execute(
                    """
                    SELECT id, payload_json FROM graph_nodes
                    WHERE work_order_id = ? AND node_type = ?
                    """,
                    (work_order_id, node_type),
                ).fetchone()
                if not row:
                    continue
                merged = {**json_loads(row["payload_json"], {}), **payload}
                conn.execute(
                    """
                    UPDATE graph_nodes
                    SET status = 'completed',
                        payload_json = ?,
                        completed_at = COALESCE(completed_at, ?)
                    WHERE id = ?
                    """,
                    (json_dumps(merged), now, row["id"]),
                )

    def _open_mr_review_gate(
        self,
        work_order_id: str,
        draft: MergeRequestDraft,
        code_review_payload: dict[str, Any],
    ) -> str:
        now = utc_now_iso()
        with connect() as conn:
            gate_id = next_public_id(conn, "G")
            gate_payload = {
                "draftId": draft.id,
                "title": draft.title,
                "description": draft.description,
                "ticketSummary": draft.ticket_summary,
                "implementationSummary": draft.implementation_summary,
                "filesModified": draft.files_modified,
                "risks": draft.risks,
                "reviewers": draft.reviewers,
                "qaChecklist": draft.qa_checklist,
                "decisionTrace": draft.decision_trace,
                "codeReviewSummary": code_review_payload.get("summary", ""),
                "scopeValidation": code_review_payload.get("scopeValidation") or {},
            }
            conn.execute(
                """
                INSERT INTO gates (
                    id, work_order_id, gate_type, status, payload_json, created_at
                ) VALUES (?, ?, ?, 'pending', ?, ?)
                """,
                (gate_id, work_order_id, MR_REVIEW_GATE_TYPE, json_dumps(gate_payload), now),
            )
            conn.execute(
                """
                UPDATE work_orders
                SET status = 'awaiting_gate', current_stage = 'mr_draft', updated_at = ?
                WHERE id = ?
                """,
                (now, work_order_id),
            )
        self.events.append(
            event_type="GATE_OPENED",
            work_order_id=work_order_id,
            actor="system",
            payload={"gateId": gate_id, "gateType": MR_REVIEW_GATE_TYPE, "draftId": draft.id},
        )
        return gate_id

    def _maybe_requeue_merge_conflicts(self, work_order_id: str) -> dict[str, Any] | None:
        from delivery_runtime.development.merge_conflicts import attempt_merge_into_target_branch
        from delivery_runtime.development.requeue import requeue_development_for_merge_conflicts
        from delivery_runtime.persistence.db import json_loads

        with connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM graph_nodes
                WHERE work_order_id = ? AND node_type = 'development' AND status = 'completed'
                ORDER BY completed_at DESC
                LIMIT 1
                """,
                (work_order_id,),
            ).fetchone()
        if not row:
            return None

        payload = json_loads(row["payload_json"], {})
        workspace_path = payload.get("workspacePath")
        if not workspace_path:
            return None

        from pathlib import Path

        workspace = Path(str(workspace_path))
        merge_result = attempt_merge_into_target_branch(workspace)
        if merge_result.ok:
            return None
        if not merge_result.conflicting_files:
            # ok=False without conflicting files means the merge could not even be
            # attempted (missing merge-target branch, not a repo, checkout failure).
            # That is a publication concern — the publisher creates the integration
            # branch on the remote — not a developer-resolvable conflict.
            return None
        return requeue_development_for_merge_conflicts(work_order_id, merge_result)


def _load_draft_context(work_order_id: str, code_review_gate_id: str) -> dict[str, Any]:
    with connect() as conn:
        wo_row = conn.execute(
            "SELECT * FROM work_orders WHERE id = ?",
            (work_order_id,),
        ).fetchone()
        if not wo_row:
            raise LookupError("Work order not found")

        gate_row = conn.execute(
            "SELECT payload_json FROM gates WHERE id = ? AND gate_type = ?",
            (code_review_gate_id, CODE_REVIEW_GATE_TYPE),
        ).fetchone()
        if not gate_row:
            raise ValueError("Approved code review gate not found")

        plan_row = conn.execute(
            """
            SELECT payload_json FROM gates
            WHERE work_order_id = ? AND gate_type = ? AND status = 'approved'
            ORDER BY approved_at DESC LIMIT 1
            """,
            (work_order_id, GATE1_TYPE),
        ).fetchone()
        impl_row = conn.execute(
            """
            SELECT payload_json FROM graph_nodes
            WHERE work_order_id = ? AND node_type = 'implementation_plan' AND status = 'completed'
            ORDER BY completed_at DESC LIMIT 1
            """,
            (work_order_id,),
        ).fetchone()
        dev_row = conn.execute(
            """
            SELECT payload_json FROM graph_nodes
            WHERE work_order_id = ? AND node_type = 'development' AND status = 'completed'
            ORDER BY completed_at DESC LIMIT 1
            """,
            (work_order_id,),
        ).fetchone()
        scope_row = conn.execute(
            "SELECT * FROM scope_contracts WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        readiness_row = None
        if wo_row["readiness_id"]:
            readiness_row = conn.execute(
                "SELECT jira_snapshot_json FROM readiness_records WHERE id = ?",
                (wo_row["readiness_id"],),
            ).fetchone()

    code_review_payload = json_loads(gate_row["payload_json"], {})
    approved_plan = json_loads(plan_row["payload_json"], {}) if plan_row else {}
    impl_payload = json_loads(impl_row["payload_json"], {}) if impl_row else {}
    dev_payload = json_loads(dev_row["payload_json"], {}) if dev_row else {}
    jira_snapshot = json_loads(readiness_row["jira_snapshot_json"], {}) if readiness_row else {}

    merged_review = {**dev_payload, **code_review_payload}
    if dev_payload.get("testRun") and "testRun" not in code_review_payload:
        merged_review["testRun"] = dev_payload["testRun"]

    scope_contract = None
    if scope_row:
        from delivery_runtime.development.scope_contract import ScopeContract

        scope_contract = ScopeContract(
            work_order_id=str(scope_row["work_order_id"]),
            allowed_files=json_loads(scope_row["allowed_files_json"], []),
            allowed_directories=json_loads(scope_row["allowed_directories_json"], []),
            forbidden_paths=json_loads(scope_row["forbidden_paths_json"], []),
            max_files_touched=int(scope_row["max_files_touched"]),
            max_lines_changed=int(scope_row["max_lines_changed"]),
        ).to_dict()

    return {
        "jira_key": str(wo_row["jira_key"]),
        "work_order_title": str(wo_row["title"]),
        "jira_snapshot": jira_snapshot,
        "approved_plan": approved_plan,
        "context_pack": impl_payload.get("contextPack") or {},
        "code_review_payload": merged_review,
        "scope_validation": merged_review.get("scopeValidation") or {},
        "scope_contract": scope_contract,
    }


def _pending_mr_gate_for_draft(work_order_id: str, draft_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, gate_type, status, payload_json
            FROM gates
            WHERE work_order_id = ?
              AND gate_type = ?
              AND status = 'pending'
              AND json_extract(payload_json, '$.draftId') = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (work_order_id, MR_REVIEW_GATE_TYPE, draft_id),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "gateType": row["gate_type"],
        "status": row["status"],
        "payload": json_loads(row["payload_json"], {}),
    }


def _pending_mr_gate_for_work_order(work_order_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, gate_type, status, payload_json
            FROM gates
            WHERE work_order_id = ? AND gate_type = ? AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (work_order_id, MR_REVIEW_GATE_TYPE),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "gateType": row["gate_type"],
        "status": row["status"],
        "payload": json_loads(row["payload_json"], {}),
    }


def get_latest_draft_for_work_order(work_order_id: str) -> MergeRequestDraft | None:
    return load_mr_draft_for_work_order(work_order_id)
