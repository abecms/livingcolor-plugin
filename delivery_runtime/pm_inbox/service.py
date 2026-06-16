"""PM Inbox service facade."""

from __future__ import annotations

import threading
from typing import Any

_ANALYSIS_LOCK = threading.Lock()

from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.events.store import EventStore
from delivery_runtime.pm_inbox.daily_pipeline import DailyAnalysisPipeline
from delivery_runtime.pm_inbox.inbox import build_pm_inbox
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.pm_inbox.queue_consumer import ExecutionQueueConsumer
from delivery_runtime.readiness.scanner import ReadinessScanner


class PmInboxService:
    def __init__(
        self,
        *,
        events: EventStore | None = None,
        scanner: ReadinessScanner | None = None,
        queue_consumer: ExecutionQueueConsumer | None = None,
    ) -> None:
        self.events = events or EventStore()
        self.scanner = scanner
        self.config = load_delivery_automation_config()
        self.pipeline = DailyAnalysisPipeline(events=self.events, scanner=scanner, config=self.config)
        self.queue_consumer = queue_consumer or ExecutionQueueConsumer(events=self.events)

    def get_inbox(self, project_key: str | None = None) -> dict[str, Any]:
        key = (project_key or self.config.project_key).strip().upper()
        from delivery_runtime.persistence.db import connect

        with connect() as conn:
            pm_store.fail_stale_daily_runs(conn)
        return build_pm_inbox(project_key=key, queue_consumer=self.queue_consumer)

    def precheck_daily_analysis(self, project_key: str | None = None) -> str:
        key = (project_key or self.config.project_key).strip().upper()
        if not key:
            raise ValueError("project_key is required")
        from delivery_runtime.persistence.db import connect
        from delivery_runtime.pm_inbox import store as pm_store

        with connect() as conn:
            pm_store.fail_stale_daily_runs(conn)
            if pm_store.has_running_daily_run(conn, project_key=key):
                raise ValueError(
                    "Another daily analysis is already running. "
                    "Wait for it to finish, then retry."
                )
        return key

    def start_daily_analysis(self, project_key: str | None = None) -> tuple[str, str]:
        """Reserve a daily-analysis run row and return (project_key, run_id)."""
        key = (project_key or self.config.project_key).strip().upper()
        if not key:
            raise ValueError("project_key is required")
        from delivery_runtime.persistence.db import connect
        from delivery_runtime.pm_inbox import store as pm_store

        with connect() as conn:
            pm_store.fail_stale_daily_runs(conn)
            if pm_store.has_running_daily_run(conn, project_key=key):
                raise ValueError(
                    "Another daily analysis is already running. "
                    "Wait for it to finish, then retry."
                )
            run_id = pm_store.create_daily_run(conn, project_key=key)
        return key, run_id

    def run_daily_analysis(
        self,
        project_key: str | None = None,
        *,
        run_id: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        key = (project_key or self.config.project_key).strip().upper()
        with _ANALYSIS_LOCK:
            result = self.pipeline.run(key, run_id=run_id, force=force)
            auto_start = self.queue_consumer.try_consume(key)
        result["autoStart"] = auto_start
        return result

    def decide_comment_proposal(
        self,
        proposal_id: str,
        *,
        action: str,
        body: str | None = None,
        actor: str = "human",
    ) -> dict[str, Any]:
        action = action.strip().lower()
        proposal = pm_store.get_comment_proposal(proposal_id)
        if not proposal:
            raise LookupError("Comment proposal not found")
        if proposal["status"] != "pending":
            raise ValueError("Only pending proposals can be updated")

        if action == "approve":
            updated = pm_store.update_comment_proposal_status(
                proposal_id=proposal_id,
                status="approved",
                body=body or proposal["body"],
                approved_by=actor,
            )
            self.events.append(
                event_type="JIRA_COMMENT_PROPOSAL_APPROVED",
                payload={"proposalId": proposal_id, "jiraKey": proposal["jiraKey"]},
                actor=actor,
            )
            return updated

        if action == "reject":
            updated = pm_store.update_comment_proposal_status(
                proposal_id=proposal_id,
                status="rejected",
                approved_by=actor,
            )
            self.events.append(
                event_type="JIRA_COMMENT_PROPOSAL_REJECTED",
                payload={"proposalId": proposal_id, "jiraKey": proposal["jiraKey"]},
                actor=actor,
            )
            return updated

        if action == "edit":
            if not body or not body.strip():
                raise ValueError("Edited comment body is required")
            updated = pm_store.update_comment_proposal_status(
                proposal_id=proposal_id,
                status="pending",
                body=body.strip(),
            )
            self.events.append(
                event_type="JIRA_COMMENT_PROPOSAL_EDITED",
                payload={"proposalId": proposal_id, "jiraKey": proposal["jiraKey"]},
                actor=actor,
            )
            return updated

        raise ValueError("action must be approve, reject, or edit")

    def update_ticket_estimation(
        self,
        *,
        project_key: str,
        jira_key: str,
        estimated_days: float,
        complexity: str | None = None,
        confidence: float | None = None,
        actor: str = "human",
    ) -> dict[str, Any]:
        from delivery_runtime.persistence.db import connect

        key = project_key.strip().upper()
        ticket_key = jira_key.strip().upper()
        record = pm_store.get_readiness_record_by_jira_key(project_key=key, jira_key=ticket_key)
        if not record:
            raise LookupError(f"Readiness record not found for {ticket_key}")

        complexity_value = (complexity or "medium").strip().lower() or "medium"
        confidence_value = float(confidence if confidence is not None else 0.75)
        with connect() as conn:
            estimation_id = pm_store.insert_estimation(
                conn,
                readiness_id=record["id"],
                jira_key=ticket_key,
                complexity=complexity_value,
                estimated_days=float(estimated_days),
                confidence=confidence_value,
                run_id="manual",
            )
        self.events.append(
            event_type="TICKET_ESTIMATION_UPDATED",
            readiness_id=record["id"],
            actor=actor,
            payload={
                "jiraKey": ticket_key,
                "estimatedDays": float(estimated_days),
                "estimationId": estimation_id,
            },
        )
        return {
            "estimationId": estimation_id,
            "readinessId": record["id"],
            "jiraKey": ticket_key,
            "estimatedDays": float(estimated_days),
            "complexity": complexity_value,
            "confidence": confidence_value,
        }

    def update_sprint_selection(
        self,
        *,
        project_key: str,
        tickets: list[str] | None = None,
        exclude: list[str] | None = None,
        swap: dict[str, str] | None = None,
        append: list[str] | None = None,
        actor: str = "human",
    ) -> dict[str, Any]:
        from delivery_runtime.pm_inbox.sprint_mutations import update_sprint_selection

        payload = update_sprint_selection(
            project_key=project_key,
            tickets=tickets,
            exclude=exclude,
            swap=swap,
            append=append,
        )
        self.events.append(
            event_type="SPRINT_SELECTION_UPDATED",
            actor=actor,
            payload={
                "projectKey": project_key.strip().upper(),
                "ticketKeys": [item["jiraKey"] for item in payload.get("tickets", [])],
            },
        )
        return payload

    def reset_sprint(self, *, project_key: str, actor: str = "human") -> dict[str, Any]:
        from delivery_runtime.pm_inbox.sprint_reset import reset_sprint

        repopulate = actor != "human"
        payload = reset_sprint(
            project_key=project_key,
            repopulate_tickets=repopulate,
            publish_report=actor != "human",
        )
        self.events.append(
            event_type="SPRINT_RESET",
            actor=actor,
            payload={"projectKey": project_key.strip().upper()},
        )
        return payload

    def publish_sprint_report(
        self,
        *,
        project_key: str,
        actor: str = "human",
        force: bool = False,
    ) -> dict[str, Any]:
        from delivery_runtime.pm_inbox.sprint_report import publish_sprint_report

        return publish_sprint_report(
            project_key=project_key,
            actor=actor,
            force=force,
        )
