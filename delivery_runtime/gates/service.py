"""Human approval gate service."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from typing import Any

from delivery_runtime.context.clarification import parse_resolved_repo_from_feedback
from delivery_runtime.development.feedback import parse_reviewer_feedback
from delivery_runtime.events.store import EventStore
from delivery_runtime.execution_graph.scheduler import mark_node_completed, reset_node_for_retry
from delivery_runtime.gates.constants import (
    CLARIFICATION_GATE_TYPE,
    CODE_REVIEW_GATE_TYPE,
    GATE1_TYPE,
    JIRA_UPDATE_GATE_TYPE,
    MR_REVIEW_GATE_TYPE,
)
from delivery_runtime.orchestration.background import schedule_orchestrator_tick
from delivery_runtime.persistence.db import connect, json_dumps, json_loads, utc_now_iso

logger = logging.getLogger(__name__)

_ESTIMATE_SKIP_REASONS = {"shadow_mode", "already_set", "no_estimate"}


class GateService:
    def __init__(
        self,
        events: EventStore | None = None,
        *,
        orchestrator: Any | None = None,
        mr_drafts: Any | None = None,
        jira_estimate_invoker_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.events = events or EventStore()
        self.orchestrator = orchestrator
        self.mr_drafts = mr_drafts
        self._jira_estimate_invoker_factory = jira_estimate_invoker_factory

    def bind_orchestrator(self, orchestrator: Any) -> None:
        self.orchestrator = orchestrator

    def bind_mr_drafts(self, mr_drafts: Any) -> None:
        self.mr_drafts = mr_drafts

    def get_gate(self, gate_id: str) -> dict[str, Any] | None:
        with connect() as conn:
            row = conn.execute("SELECT * FROM gates WHERE id = ?", (gate_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def approve(self, gate_id: str, *, approved_by: str = "human") -> dict[str, Any]:
        gate = self.get_gate(gate_id)
        if not gate:
            raise LookupError("Gate not found")
        if gate["status"] != "pending":
            raise ValueError("Only pending gates can be approved or rejected")

        if gate["gateType"] == MR_REVIEW_GATE_TYPE:
            draft_id = str((gate.get("payload") or {}).get("draftId") or "")
            if not draft_id:
                raise ValueError("MR review gate missing draftId")
            self._mr_draft_service().approve_draft(draft_id, approved_by=approved_by)
            updated_gate = self.get_gate(gate_id)
            if not updated_gate:
                raise RuntimeError("Gate approval failed")
            return {"gate": updated_gate, "workOrderId": gate["workOrderId"]}

        with connect() as conn:
            gate = self._require_pending_gate(conn, gate_id)
            now = utc_now_iso()
            conn.execute(
                """
                UPDATE gates
                SET status = 'approved', approved_at = ?, approved_by = ?
                WHERE id = ?
                """,
                (now, approved_by, gate_id),
            )
            if gate["gateType"] == CLARIFICATION_GATE_TYPE:
                node_id = str((gate.get("payload") or {}).get("nodeId") or "")
                if node_id:
                    reset_node_for_retry(conn, node_id, payload={})
                next_status, next_stage = "running", "analysis_review"
            else:
                next_status, next_stage = self._next_state_after_approval(gate["gateType"])
            conn.execute(
                """
                UPDATE work_orders
                SET status = ?, current_stage = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_status, next_stage, now, gate["workOrderId"]),
            )
            self.events.append(
                event_type="GATE_APPROVED",
                work_order_id=gate["workOrderId"],
                actor=approved_by,
                payload={"gateId": gate_id, "gateType": gate["gateType"]},
                conn=conn,
            )
            work_order_id = gate["workOrderId"]
            if gate["gateType"] == JIRA_UPDATE_GATE_TYPE:
                self._complete_jira_update(conn, work_order_id, gate.get("payload") or {})

        jira_estimate_writeback: dict[str, Any] | None = None
        if gate["gateType"] == GATE1_TYPE:
            from delivery_runtime.development.scope_store import create_scope_contract_for_gate_approval

            create_scope_contract_for_gate_approval(work_order_id, gate.get("payload") or {})
            jira_estimate_writeback = self._write_estimate_back_to_jira(
                work_order_id,
                overwrite=True,
            )

        if gate["gateType"] == CODE_REVIEW_GATE_TYPE:
            mr_service = self._mr_draft_service()
            mr_service.create_draft_after_code_review(
                work_order_id,
                code_review_gate_id=gate_id,
            )

        if self.orchestrator and gate["gateType"] in {GATE1_TYPE, CLARIFICATION_GATE_TYPE}:
            schedule_orchestrator_tick(self.orchestrator, work_order_id)

        updated_gate = self.get_gate(gate_id)
        if not updated_gate:
            raise RuntimeError("Gate approval failed")
        result: dict[str, Any] = {"gate": updated_gate, "workOrderId": work_order_id}
        if jira_estimate_writeback is not None:
            result["jiraEstimateWriteback"] = jira_estimate_writeback
        return result

    def reject(
        self,
        gate_id: str,
        *,
        feedback: str,
        rejected_by: str = "human",
        structured_feedback: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        feedback = feedback.strip()
        if not feedback and not structured_feedback:
            raise ValueError("Rejection feedback is required")

        gate = self.get_gate(gate_id)
        if not gate:
            raise LookupError("Gate not found")
        if gate["status"] != "pending":
            raise ValueError("Only pending gates can be approved or rejected")

        if gate["gateType"] == MR_REVIEW_GATE_TYPE:
            draft_id = str((gate.get("payload") or {}).get("draftId") or "")
            if not draft_id:
                raise ValueError("MR review gate missing draftId")
            self._mr_draft_service().reject_draft(
                draft_id,
                feedback=feedback,
                rejected_by=rejected_by,
            )
            updated_gate = self.get_gate(gate_id)
            if not updated_gate:
                raise RuntimeError("Gate rejection failed")
            return {"gate": updated_gate, "workOrderId": gate["workOrderId"]}

        with connect() as conn:
            gate = self._require_pending_gate(conn, gate_id)
            if gate["gateType"] not in {
                GATE1_TYPE,
                CLARIFICATION_GATE_TYPE,
                CODE_REVIEW_GATE_TYPE,
                MR_REVIEW_GATE_TYPE,
            }:
                raise ValueError("Unsupported gate type for rejection")

            node_id = str((gate.get("payload") or {}).get("nodeId") or "")
            if not node_id:
                raise ValueError("Gate payload is missing nodeId")

            node_row = conn.execute(
                "SELECT payload_json, node_type FROM graph_nodes WHERE id = ? AND work_order_id = ?",
                (node_id, gate["workOrderId"]),
            ).fetchone()
            if not node_row:
                raise ValueError("Linked graph node not found")

            retry_node_id = node_id
            retry_node_payload = json_loads(node_row["payload_json"], {})
            if gate["gateType"] == CODE_REVIEW_GATE_TYPE and node_row["node_type"] != "development":
                dev_row = conn.execute(
                    """
                    SELECT id, payload_json FROM graph_nodes
                    WHERE work_order_id = ? AND node_type = 'development'
                    ORDER BY rowid ASC
                    LIMIT 1
                    """,
                    (gate["workOrderId"],),
                ).fetchone()
                if not dev_row:
                    raise ValueError("Development node not found for code review rejection")
                retry_node_id = str(dev_row["id"])
                retry_node_payload = json_loads(dev_row["payload_json"], {})

            now = utc_now_iso()
            conn.execute(
                """
                UPDATE gates
                SET status = 'rejected', rejection_feedback = ?, approved_by = ?
                WHERE id = ?
                """,
                (feedback, rejected_by, gate_id),
            )

            node_payload = retry_node_payload
            node_payload["rejectionFeedback"] = feedback
            if gate["gateType"] == CLARIFICATION_GATE_TYPE:
                resolved_repo = parse_resolved_repo_from_feedback(feedback)
                if resolved_repo:
                    node_payload["resolvedRepo"] = resolved_repo
            elif gate["gateType"] == CODE_REVIEW_GATE_TYPE:
                node_payload["reviewerFeedback"] = structured_feedback or parse_reviewer_feedback(feedback)
                node_payload.pop("developerPhase", None)

            reset_node_for_retry(conn, retry_node_id, payload=node_payload)

            if gate["gateType"] == CODE_REVIEW_GATE_TYPE:
                from delivery_runtime.development.requeue import reset_pipeline_after_development_retry

                reset_pipeline_after_development_retry(conn, gate["workOrderId"])

            reject_stage = (
                "analysis_review"
                if gate["gateType"] in {GATE1_TYPE, CLARIFICATION_GATE_TYPE}
                else "development"
            )
            conn.execute(
                """
                UPDATE work_orders
                SET status = 'running', current_stage = ?, updated_at = ?
                WHERE id = ?
                """,
                (reject_stage, now, gate["workOrderId"]),
            )
            self.events.append(
                event_type="GATE_REJECTED",
                work_order_id=gate["workOrderId"],
                actor=rejected_by,
                payload={"gateId": gate_id, "gateType": gate["gateType"], "feedback": feedback},
                conn=conn,
            )
            work_order_id = gate["workOrderId"]

        if self.orchestrator:
            schedule_orchestrator_tick(self.orchestrator, work_order_id)

        updated_gate = self.get_gate(gate_id)
        if not updated_gate:
            raise RuntimeError("Gate rejection failed")
        return {"gate": updated_gate, "workOrderId": work_order_id}

    def _write_estimate_back_to_jira(
        self,
        work_order_id: str,
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Best-effort Jira originalEstimate write-back at analysis approval.

        Never raises — gate approval must succeed even when Jira is down or
        no invoker is wired (non-server contexts).
        """
        jira_key = ""
        try:
            if self._jira_estimate_invoker_factory is None:
                return {"written": False, "reason": "invoker_not_configured"}

            from delivery_runtime.jira.estimate_writeback import write_estimate_to_jira

            estimated_days, jira_key = self._resolve_work_order_estimate_days(work_order_id)
            if not jira_key:
                return {"written": False, "reason": "missing_jira_key"}

            invoker = self._jira_estimate_invoker_factory()
            result = write_estimate_to_jira(
                jira_key,
                estimated_days,
                invoker=invoker,
                overwrite=overwrite,
            )

            if result.get("written"):
                event_type = "JIRA_ESTIMATE_WRITTEN"
            elif result.get("reason") in _ESTIMATE_SKIP_REASONS:
                event_type = "JIRA_ESTIMATE_WRITE_SKIPPED"
            else:
                event_type = "JIRA_ESTIMATE_WRITE_FAILED"
            self.events.append(
                event_type=event_type,
                work_order_id=work_order_id,
                actor="system",
                payload={"jiraKey": jira_key, **result},
            )
            return {"jiraKey": jira_key, **result}
        except Exception as exc:
            logger.exception(
                "Jira estimate write-back failed for work order %s", work_order_id
            )
            failure = {"jiraKey": jira_key, "written": False, "reason": str(exc)}
            try:
                self.events.append(
                    event_type="JIRA_ESTIMATE_WRITE_FAILED",
                    work_order_id=work_order_id,
                    actor="system",
                    payload=failure,
                )
            except Exception:
                logger.exception(
                    "Could not record estimate write-back failure event for work order %s",
                    work_order_id,
                )
            return failure

    @staticmethod
    def _resolve_work_order_estimate_days(work_order_id: str) -> tuple[float | None, str]:
        with connect() as conn:
            row = conn.execute(
                """
                SELECT wo.jira_key AS jira_key,
                       rr.estimated_days AS estimated_days,
                       rr.jira_snapshot_json AS jira_snapshot_json,
                       rr.readiness_score AS readiness_score,
                       rr.confidence AS confidence
                FROM work_orders wo
                LEFT JOIN readiness_records rr ON rr.id = wo.readiness_id
                WHERE wo.id = ?
                """,
                (work_order_id,),
            ).fetchone()
        if not row:
            return None, ""

        jira_key = str(row["jira_key"] or "").strip()
        estimated_days = row["estimated_days"]
        if not estimated_days:
            from delivery_runtime.pm_inbox.estimation import estimate_ticket_effort

            snapshot = json_loads(row["jira_snapshot_json"], {})
            estimation = estimate_ticket_effort(
                snapshot if isinstance(snapshot, dict) else {},
                readiness_score=int(row["readiness_score"] or 70),
                confidence=float(row["confidence"] or 0.6),
            )
            estimated_days = estimation.estimated_days
        return estimated_days, jira_key

    @staticmethod
    def _next_state_after_approval(gate_type: str) -> tuple[str, str]:
        if gate_type == CODE_REVIEW_GATE_TYPE:
            return "running", "awaiting_next_phase"
        if gate_type == MR_REVIEW_GATE_TYPE:
            return "running", "awaiting_next_phase"
        if gate_type == JIRA_UPDATE_GATE_TYPE:
            return "completed", "completed"
        return "running", "development"

    @staticmethod
    def _complete_jira_update(
        conn: sqlite3.Connection,
        work_order_id: str,
        gate_payload: dict[str, Any],
    ) -> None:
        row = conn.execute(
            """
            SELECT id, status, payload_json FROM graph_nodes
            WHERE work_order_id = ? AND node_type = 'jira_update'
            ORDER BY rowid ASC
            LIMIT 1
            """,
            (work_order_id,),
        ).fetchone()
        if not row or row["status"] == "completed":
            return

        jira_key = str(gate_payload.get("jiraKey") or "").strip()
        if not jira_key:
            wo = conn.execute(
                "SELECT jira_key FROM work_orders WHERE id = ?",
                (work_order_id,),
            ).fetchone()
            jira_key = str(wo["jira_key"] or "") if wo else ""
        project_key = jira_key.split("-")[0] if "-" in jira_key else jira_key
        comment_body = str(gate_payload.get("proposedComment") or "").strip()

        jira_result = GateService._write_delivery_completion_to_jira(
            jira_key,
            comment_body,
            project_key=project_key,
            work_order_id=work_order_id,
        )

        node_payload = {
            **json_loads(row["payload_json"], {}),
            "status": "approved",
            "mrUrl": gate_payload.get("mrUrl"),
            "mrIid": gate_payload.get("mrIid"),
            "proposedComment": gate_payload.get("proposedComment"),
            "source": "human_gate",
            "jiraWriteback": jira_result,
        }
        mark_node_completed(conn, str(row["id"]), node_payload)

    @staticmethod
    def _write_delivery_completion_to_jira(
        jira_key: str,
        comment_body: str,
        *,
        project_key: str,
        work_order_id: str,
    ) -> dict[str, Any]:
        """Best-effort Jira comment + transition at delivery completion."""
        try:
            from delivery_runtime.jira.delivery_writeback import write_delivery_completion_to_jira

            return write_delivery_completion_to_jira(
                jira_key,
                comment_body,
                project_key=project_key,
            )
        except Exception as exc:
            logger.exception("Jira delivery write-back failed for work order %s", work_order_id)
            return {"commentPosted": False, "transitionApplied": False, "reason": str(exc)}

    def _mr_draft_service(self):
        if self.mr_drafts is not None:
            return self.mr_drafts
        from delivery_runtime.mr_drafts.service import MrDraftService

        self.mr_drafts = MrDraftService(events=self.events)
        return self.mr_drafts

    @staticmethod
    def _require_pending_gate(conn: sqlite3.Connection, gate_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM gates WHERE id = ?", (gate_id,)).fetchone()
        if not row:
            raise LookupError("Gate not found")
        gate = GateService._row_to_dict(row)
        if gate["status"] != "pending":
            raise ValueError("Only pending gates can be approved or rejected")
        return gate

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "workOrderId": row["work_order_id"],
            "gateType": row["gate_type"],
            "status": row["status"],
            "payload": json_loads(row["payload_json"], {}),
            "createdAt": row["created_at"],
            "approvedAt": row["approved_at"],
            "approvedBy": row["approved_by"],
            "rejectionFeedback": row["rejection_feedback"],
        }
