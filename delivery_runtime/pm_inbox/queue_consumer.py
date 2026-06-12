"""Automatic consumption of the LivingColor execution queue."""

from __future__ import annotations

import sqlite3
from typing import Any

from delivery_runtime.automation.config import DeliveryAutomationConfig, load_delivery_automation_config
from delivery_runtime.events.store import EventStore
from delivery_runtime.persistence.db import connect, utc_now_iso
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.pm_inbox.project_memory import build_project_memory_highlights, collect_project_memory


class ExecutionQueueConsumer:
    """Start development automatically from execution queue item #1."""

    def __init__(
        self,
        *,
        events: EventStore | None = None,
        work_orders: Any | None = None,
        readiness: Any | None = None,
        orchestrator: Any | None = None,
        config: DeliveryAutomationConfig | None = None,
    ) -> None:
        self.events = events or EventStore()
        self.work_orders = work_orders
        self.readiness = readiness
        self.orchestrator = orchestrator
        self.config = config or load_delivery_automation_config()

    def try_consume(self, project_key: str | None = None) -> dict[str, Any]:
        """Create and launch a work order when no active BN development exists."""
        project_key = (project_key or self.config.project_key).strip().upper()
        if not self.work_orders or not self.readiness or not self.orchestrator:
            return {"started": False, "reason": "consumer_not_wired"}

        active = self.get_active_development(project_key)
        if active:
            return {
                "started": False,
                "reason": "active_development_exists",
                "activeDevelopment": active,
            }

        candidate = self._select_queue_candidate(project_key)
        if not candidate:
            return {"started": False, "reason": "no_executable_candidate"}

        record = self.readiness.get_record(str(candidate["readinessId"]))
        if not record:
            return {"started": False, "reason": "readiness_record_missing", "jiraKey": candidate["jiraKey"]}
        if record["readinessStatus"] != "ready":
            return {
                "started": False,
                "reason": "readiness_not_ready",
                "jiraKey": candidate["jiraKey"],
                "readinessStatus": record["readinessStatus"],
            }

        if pm_store.readiness_has_pending_proposal(readiness_id=record["id"]):
            return {
                "started": False,
                "reason": "awaiting_human_approval",
                "jiraKey": candidate["jiraKey"],
            }

        started_at = utc_now_iso()
        pm_store.mark_queue_item_in_progress(
            project_key=project_key,
            jira_key=candidate["jiraKey"],
            readiness_id=record["id"],
            started_at=started_at,
        )

        work_order_id: str | None = None
        try:
            work_order = self.work_orders.create_from_readiness(record, actor="system")
            work_order_id = work_order["id"]
            pm_store.attach_work_order_to_queue_item(
                project_key=project_key,
                jira_key=candidate["jiraKey"],
                work_order_id=work_order_id,
            )
            self.orchestrator.tick(work_order_id)
            refreshed = self.work_orders.get_work_order(work_order_id) or work_order
            self._record_queue_start_memory(
                project_key=project_key,
                jira_key=candidate["jiraKey"],
                work_order_id=work_order_id,
                queue_position=int(candidate.get("position") or 1),
                started_at=started_at,
            )
            self.events.append(
                event_type="EXECUTION_QUEUE_CONSUMED",
                work_order_id=work_order_id,
                readiness_id=record["id"],
                actor="system",
                payload={
                    "projectKey": project_key,
                    "jiraKey": candidate["jiraKey"],
                    "priorityScore": candidate.get("priorityScore"),
                    "queuePosition": candidate.get("position"),
                },
            )
            return {
                "started": True,
                "workOrderId": work_order_id,
                "jiraKey": candidate["jiraKey"],
                "queuePosition": candidate.get("position"),
                "workOrder": refreshed,
            }
        except Exception as exc:
            self.handle_development_failure(
                project_key=project_key,
                jira_key=candidate["jiraKey"],
                readiness_id=record["id"],
                work_order_id=work_order_id,
                reason=str(exc),
            )
            return {
                "started": False,
                "reason": "auto_start_failed",
                "jiraKey": candidate["jiraKey"],
                "error": str(exc),
            }

    def handle_development_failure(
        self,
        *,
        project_key: str,
        jira_key: str,
        readiness_id: str | None = None,
        work_order_id: str | None = None,
        reason: str,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Return a ticket to the queue and persist failure context."""
        now = utc_now_iso()

        def apply_state_updates(connection: sqlite3.Connection) -> None:
            if work_order_id:
                connection.execute(
                    """
                    UPDATE work_orders
                    SET status = 'failed', current_stage = 'completed', updated_at = ?
                    WHERE id = ?
                    """,
                    (now, work_order_id),
                )
            if readiness_id:
                confidence_row = connection.execute(
                    "SELECT confidence FROM readiness_records WHERE id = ?",
                    (readiness_id,),
                ).fetchone()
                reduced = 0.1
                if confidence_row:
                    reduced = max(0.1, float(confidence_row["confidence"]) * 0.85)
                connection.execute(
                    """
                    UPDATE readiness_records
                    SET readiness_status = 'ready',
                        promoted_work_order_id = NULL,
                        confidence = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (reduced, now, readiness_id),
                )

        if conn is not None:
            apply_state_updates(conn)
        else:
            with connect() as owned:
                apply_state_updates(owned)

        pm_store.release_queue_item(
            project_key=project_key,
            jira_key=jira_key,
            failure_reason=reason,
            conn=conn,
        )
        memory = collect_project_memory(project_key=project_key)
        failures = list(memory.get("recentFailures") or [])
        failures.insert(
            0,
            {
                "jiraKey": jira_key,
                "reason": reason,
                "failedAt": now,
                "workOrderId": work_order_id,
            },
        )
        memory["recentFailures"] = failures[:20]
        if conn is not None:
            pm_store.upsert_project_memory(
                conn,
                project_key=project_key,
                memory=memory,
                highlights=build_project_memory_highlights(memory),
            )
        else:
            with connect() as owned:
                pm_store.upsert_project_memory(
                    owned,
                    project_key=project_key,
                    memory=memory,
                    highlights=build_project_memory_highlights(memory),
                )
        self.events.append(
            event_type="EXECUTION_QUEUE_RELEASED",
            work_order_id=work_order_id,
            readiness_id=readiness_id,
            actor="system",
            payload={"projectKey": project_key, "jiraKey": jira_key, "reason": reason},
        )

    def get_active_development(self, project_key: str) -> dict[str, Any] | None:
        prefix = f"{project_key.strip().upper()}-%"
        with connect() as conn:
            row = conn.execute(
                """
                SELECT wo.*, rr.confidence AS readiness_confidence
                FROM work_orders wo
                LEFT JOIN readiness_records rr ON rr.id = wo.readiness_id
                WHERE wo.jira_key LIKE ?
                  AND wo.status NOT IN ('completed', 'cancelled', 'failed')
                ORDER BY wo.updated_at DESC
                LIMIT 1
                """,
                (prefix,),
            ).fetchone()
            if not row:
                return None

            estimation = None
            if row["readiness_id"]:
                est_row = conn.execute(
                    """
                    SELECT complexity, estimated_days, confidence
                    FROM ticket_estimations
                    WHERE readiness_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (row["readiness_id"],),
                ).fetchone()
                if est_row:
                    estimation = {
                        "complexity": est_row["complexity"],
                        "estimatedDays": est_row["estimated_days"],
                        "confidence": est_row["confidence"],
                    }

            pending_gate = conn.execute(
                """
                SELECT gate_type, status FROM gates
                WHERE work_order_id = ? AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (row["id"],),
            ).fetchone()

        return {
            "workOrderId": row["id"],
            "jiraKey": row["jira_key"],
            "title": row["title"],
            "status": row["status"],
            "currentStage": row["current_stage"],
            "startedAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "currentPhase": _phase_label(row["status"], row["current_stage"], pending_gate),
            "estimation": estimation,
        }

    def _select_queue_candidate(self, project_key: str) -> dict[str, Any] | None:
        queue = pm_store.get_execution_queue(project_key=project_key)
        for item in queue.get("items") or []:
            if int(item.get("position") or 0) != 1:
                continue
            if item.get("queueStatus") != "executable":
                return None
            return item
        return None

    @staticmethod
    def _record_queue_start_memory(
        *,
        project_key: str,
        jira_key: str,
        work_order_id: str,
        queue_position: int,
        started_at: str,
    ) -> None:
        memory = collect_project_memory(project_key=project_key)
        starts = list(memory.get("recentQueueStarts") or [])
        starts.insert(
            0,
            {
                "jiraKey": jira_key,
                "workOrderId": work_order_id,
                "queuePosition": queue_position,
                "startedAt": started_at,
            },
        )
        memory["recentQueueStarts"] = starts[:20]
        memory["currentQueueSelection"] = {
            "jiraKey": jira_key,
            "workOrderId": work_order_id,
            "queuePosition": queue_position,
            "startedAt": started_at,
        }
        with connect() as conn:
            pm_store.upsert_project_memory(
                conn,
                project_key=project_key,
                memory=memory,
                highlights=build_project_memory_highlights(memory),
            )


def _phase_label(status: str, stage: str, pending_gate) -> str:
    if status == "awaiting_gate" and pending_gate:
        gate_type = str(pending_gate["gate_type"])
        if gate_type == "analysis_plan":
            return "Analysis Gate"
        if gate_type == "code_review":
            return "Patch Review"
        if gate_type in {"merge_request_review", "merge_request"}:
            return "MR Review"
        if gate_type == "jira_update":
            return "Jira Update"
        return "Awaiting Approval"
    if stage == "development" or (status == "running" and stage == "development"):
        return "Patch Generation"
    if stage == "intake" or stage == "analysis_review":
        return "Implementation Plan"
    return stage.replace("_", " ").title()
