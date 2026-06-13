"""Daily BN delivery analysis pipeline."""

from __future__ import annotations

from typing import Any

from delivery_runtime.automation.config import DeliveryAutomationConfig, load_delivery_automation_config
from delivery_runtime.events.store import EventStore
from delivery_runtime.persistence.db import connect, json_dumps, utc_now_iso
from delivery_runtime.pm_inbox.analyst import analyze_for_daily_delivery
from delivery_runtime.pm_inbox.estimation import estimate_ticket_effort
from delivery_runtime.pm_inbox.execution_queue import build_execution_queue, execution_queue_to_dict
from delivery_runtime.pm_inbox.project_memory import (
    build_project_memory_highlights,
    collect_project_memory,
)
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.readiness.errors import ReadinessIntegrationError
from delivery_runtime.readiness.scanner import ReadinessScanner
from delivery_runtime.readiness.ticket_scope import load_ticket_scope_for_project, matches_ticket_scope


class DailyAnalysisPipeline:
    def __init__(
        self,
        *,
        events: EventStore | None = None,
        scanner: ReadinessScanner | None = None,
        config: DeliveryAutomationConfig | None = None,
    ) -> None:
        self.events = events or EventStore()
        self.scanner = scanner or ReadinessScanner(self.events)
        self.config = config or load_delivery_automation_config()

    def run(self, project_key: str | None = None) -> dict[str, Any]:
        project_key = (project_key or self.config.project_key).strip().upper()
        if not project_key:
            raise ValueError("project_key is required")

        with connect() as conn:
            pm_store.fail_stale_daily_runs(conn)
            if pm_store.has_running_daily_run(conn):
                raise ValueError(
                    "Another daily analysis is already running. "
                    "Wait for it to finish, then retry."
                )
            run_id = pm_store.create_daily_run(conn, project_key=project_key)

        self.events.append(
            event_type="DAILY_ANALYSIS_STARTED",
            payload={"projectKey": project_key, "runId": run_id},
        )

        try:
            if self.scanner._issue_fetcher is None:
                raise ReadinessIntegrationError("Jira integration is not configured on this server")

            scan_result = self.scanner.scan_project(project_key)
            enhanced = self._qualify_and_estimate(project_key=project_key, run_id=run_id)
            execution_queue = self._rebuild_execution_queue(project_key=project_key, run_id=run_id)
            selected_sprint = self._rebuild_selected_sprint(project_key=project_key)
            project_memory = self._refresh_project_memory(project_key=project_key, run_id=run_id)

            pipeline_payload = {
                "scan": {
                    "fetched": scan_result.fetched,
                    "scanned": scan_result.fetched,
                    "inScope": scan_result.in_scope,
                    "created": scan_result.created,
                    "updated": scan_result.updated,
                    "skipped": scan_result.skipped,
                    "skippedOutOfScope": scan_result.skipped_out_of_scope,
                    "skippedExcluded": scan_result.skipped_excluded,
                    "dismissedOutOfScope": scan_result.dismissed_out_of_scope,
                },
                "qualification": enhanced,
                "executionQueue": execution_queue,
                "selectedSprint": selected_sprint,
                "projectMemory": project_memory,
            }

            with connect() as conn:
                pm_store.complete_daily_run(
                    conn,
                    run_id=run_id,
                    status="completed",
                    jira_synced=scan_result.in_scope,
                    analyzed=enhanced["analyzed"],
                    estimated=enhanced["estimated"],
                    pipeline=pipeline_payload,
                )

            self.events.append(
                event_type="DAILY_ANALYSIS_COMPLETED",
                payload={"projectKey": project_key, "runId": run_id},
            )
            return {"runId": run_id, "projectKey": project_key, **pipeline_payload}
        except Exception as exc:
            with connect() as conn:
                pm_store.complete_daily_run(
                    conn,
                    run_id=run_id,
                    status="failed",
                    jira_synced=0,
                    analyzed=0,
                    estimated=0,
                    pipeline={},
                    error_message=str(exc),
                )
            self.events.append(
                event_type="DAILY_ANALYSIS_FAILED",
                payload={"projectKey": project_key, "runId": run_id, "error": str(exc)},
            )
            raise

    def _qualify_and_estimate(self, *, project_key: str, run_id: str) -> dict[str, Any]:
        analyzed = estimated = proposals_created = 0
        ticket_scope = load_ticket_scope_for_project(project_key)

        with connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM readiness_records
                WHERE project_key = ? AND readiness_status NOT IN ('promoted', 'dismissed')
                ORDER BY updated_at DESC
                """,
                (project_key,),
            ).fetchall()

            for row in rows:
                snapshot = json_loads_safe(row["jira_snapshot_json"])
                if not matches_ticket_scope(snapshot, ticket_scope):
                    continue
                analysis = analyze_for_daily_delivery(snapshot)
                now = utc_now_iso()
                conn.execute(
                    """
                    UPDATE readiness_records SET
                        readiness_score = ?,
                        readiness_status = ?,
                        analysis_summary = ?,
                        blockers_json = ?,
                        confidence = ?,
                        analyzed_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        analysis["readinessScore"],
                        analysis["readinessStatus"],
                        analysis["analysisSummary"],
                        json_dumps(analysis["blockers"]),
                        analysis["confidence"],
                        now,
                        now,
                        row["id"],
                    ),
                )
                analyzed += 1

                if analysis.get("proposedComment") and analysis.get("proposalType"):
                    pm_store.upsert_comment_proposal(
                        conn,
                        readiness_id=row["id"],
                        jira_key=row["jira_key"],
                        proposal_type=str(analysis["proposalType"]),
                        body=str(analysis["proposedComment"]),
                    )
                    proposals_created += 1

                if analysis.get("actionable"):
                    estimation = estimate_ticket_effort(
                        snapshot,
                        readiness_score=int(analysis["readinessScore"]),
                        confidence=float(analysis["confidence"]),
                    )
                    pm_store.insert_estimation(
                        conn,
                        readiness_id=row["id"],
                        jira_key=row["jira_key"],
                        complexity=estimation.complexity,
                        estimated_days=estimation.estimated_days,
                        confidence=estimation.confidence,
                        run_id=run_id,
                    )
                    estimated += 1

        return {
            "analyzed": analyzed,
            "estimated": estimated,
            "proposalsCreated": proposals_created,
        }

    def refresh_communications(self, project_key: str | None = None) -> dict[str, Any]:
        """Regenerate Jira comment proposals using the current communication language."""
        project_key = (project_key or self.config.project_key).strip().upper()
        if not project_key:
            raise ValueError("project_key is required")

        result = self._qualify_and_estimate(project_key=project_key, run_id="COMM-REFRESH")
        self.events.append(
            event_type="PROJECT_COMMUNICATIONS_REFRESHED",
            payload={"projectKey": project_key, **result},
        )
        return {"projectKey": project_key, **result}

    def _rebuild_execution_queue(self, *, project_key: str, run_id: str) -> dict[str, Any]:
        latest_estimations = pm_store.latest_estimations_by_readiness(project_key=project_key)
        existing_memory = pm_store.get_project_memory(project_key=project_key)
        memory_payload = (existing_memory or {}).get("memory") or {}
        ticket_scope = load_ticket_scope_for_project(project_key)

        tickets: list[dict[str, Any]] = []
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM readiness_records
                WHERE project_key = ? AND readiness_status NOT IN ('promoted', 'dismissed')
                ORDER BY updated_at DESC
                """,
                (project_key,),
            ).fetchall()

            for row in rows:
                snapshot = json_loads_safe(row["jira_snapshot_json"])
                if not matches_ticket_scope(snapshot, ticket_scope):
                    continue
                estimation = latest_estimations.get(row["id"])
                tickets.append(
                    {
                        "readinessId": row["id"],
                        "jiraKey": row["jira_key"],
                        "title": row["title"],
                        "readinessStatus": row["readiness_status"],
                        "readinessScore": row["readiness_score"],
                        "blockers": json_loads_safe_list(row["blockers_json"]),
                        "jiraSnapshot": json_loads_safe(row["jira_snapshot_json"]),
                        "estimation": estimation,
                    }
                )

        snapshot = build_execution_queue(
            project_key=project_key,
            tickets=tickets,
            project_memory=memory_payload,
        )
        payload = execution_queue_to_dict(snapshot)
        store_items = []
        for item in payload["items"]:
            store_items.append(
                {
                    "readinessId": item["readiness_id"],
                    "jiraKey": item["jira_key"],
                    "title": item["title"],
                    "queueStatus": item["queue_status"],
                    "priorityScore": item["priority_score"],
                    "estimatedDays": item["estimated_days"],
                    "complexity": item["complexity"],
                    "confidence": item["confidence"],
                    "blockers": item["blockers"],
                    "priorityFactors": item["priority_factors"],
                    "position": item["position"],
                    "recommendedNext": item["recommended_next"],
                }
            )

        with connect() as conn:
            pm_store.replace_execution_queue(
                conn,
                project_key=project_key,
                items=store_items,
                run_id=run_id,
            )

        return payload

    def _rebuild_selected_sprint(self, *, project_key: str) -> dict[str, Any]:
        from delivery_runtime.pm_inbox.sprint_selection import build_selected_sprint_payload, persist_selected_sprint
        from delivery_runtime.pm_inbox import store as pm_store

        state = pm_store.get_sprint_state(project_key=project_key)
        memory = (state or {}).get("memory") or {}
        if isinstance(memory, dict) and memory.get("manualOverride"):
            return (state or {}).get("recommendation") or build_selected_sprint_payload(project_key=project_key)

        payload = build_selected_sprint_payload(project_key=project_key)
        persist_selected_sprint(project_key=project_key, payload=payload)
        return payload

    def _refresh_project_memory(self, *, project_key: str, run_id: str) -> dict[str, Any]:
        from delivery_runtime.pm_inbox.repo_architecture import merge_repo_architecture

        memory = collect_project_memory(project_key=project_key)
        memory = merge_repo_architecture(memory, project_key=project_key)
        memory["lastRunId"] = run_id
        highlights = build_project_memory_highlights(memory)
        with connect() as conn:
            pm_store.upsert_project_memory(
                conn,
                project_key=project_key,
                memory=memory,
                highlights=highlights,
            )
        return {"memory": memory, "highlights": highlights}


def refresh_project_communications(project_key: str | None = None) -> dict[str, Any]:
    """Refresh pending Jira comment proposals for the configured communication language."""
    pipeline = DailyAnalysisPipeline()
    return pipeline.refresh_communications(project_key)


def json_loads_safe(raw: str | None) -> dict[str, Any]:
    from delivery_runtime.persistence.db import json_loads

    loaded = json_loads(raw, {})
    return loaded if isinstance(loaded, dict) else {}


def json_loads_safe_list(raw: str | None) -> list[Any]:
    from delivery_runtime.persistence.db import json_loads

    loaded = json_loads(raw, [])
    return loaded if isinstance(loaded, list) else []
