"""Readiness queue service."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

from delivery_runtime.events.store import EventStore
from delivery_runtime.persistence.db import connect, json_dumps, json_loads, utc_now_iso
from delivery_runtime.readiness.analyzer import analyze_ticket_snapshot
from delivery_runtime.readiness.errors import ReadinessIntegrationError
from delivery_runtime.readiness.scanner import ReadinessScanner
from delivery_runtime.work_orders.service import WorkOrderService


class ReadinessService:
    def __init__(
        self,
        events: EventStore | None = None,
        scanner: ReadinessScanner | None = None,
        work_orders: WorkOrderService | None = None,
        *,
        orchestrator: Any | None = None,
        analysis_runner: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
        issue_refresher: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.events = events or EventStore()
        self.scanner = scanner or ReadinessScanner(self.events)
        self.work_orders = work_orders or WorkOrderService(self.events)
        self.orchestrator = orchestrator
        self._analysis_runner = analysis_runner
        self._issue_refresher = issue_refresher

    def list_records(
        self,
        *,
        status: str | None = None,
        project_key: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = ["readiness_status NOT IN ('promoted', 'dismissed')"]
        params: list[Any] = []

        if status:
            clauses.append("readiness_status = ?")
            params.append(status)
        if project_key:
            clauses.append("project_key = ?")
            params.append(project_key)

        where = " AND ".join(clauses)
        with connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM readiness_records
                WHERE {where}
                ORDER BY readiness_score DESC, updated_at DESC
                """,
                params,
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_record(self, record_id: str) -> dict[str, Any] | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM readiness_records WHERE id = ?",
                (record_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def scan_project(self, project_key: str) -> dict[str, Any]:
        result = self.scanner.scan_project(project_key)
        return {
            "projectKey": result.project_key,
            "scanned": result.scanned,
            "created": result.created,
            "updated": result.updated,
            "skipped": result.skipped,
        }

    def promote(self, record_id: str, *, actor: str = "human", tick: bool = True) -> dict[str, Any]:
        record = self.get_record(record_id)
        if not record:
            raise LookupError("Readiness record not found")
        if record["readinessStatus"] != "ready":
            raise ValueError("Only ready tickets can be promoted to a work order")
        work_order = self.work_orders.create_from_readiness(record, actor=actor)
        if tick:
            work_order = self._run_orchestrator_tick(work_order)
        self._mark_queue_item_in_progress(record, work_order)
        return work_order

    def run_orchestrator_tick(self, work_order_id: str) -> None:
        """Advance a work order graph; safe to call from a background task."""
        work_order = self.work_orders.get_work_order(work_order_id)
        if not work_order:
            return
        self._run_orchestrator_tick(work_order)

    def _run_orchestrator_tick(self, work_order: dict[str, Any]) -> dict[str, Any]:
        if not self.orchestrator:
            return work_order
        try:
            self.orchestrator.tick(work_order["id"])
        except Exception:
            pass
        refreshed = self.work_orders.get_work_order(work_order["id"])
        return refreshed or work_order

    @staticmethod
    def _mark_queue_item_in_progress(record: dict[str, Any], work_order: dict[str, Any]) -> None:
        from delivery_runtime.persistence.db import utc_now_iso
        from delivery_runtime.pm_inbox import store as pm_store

        project_key = str(record.get("projectKey") or work_order.get("jiraKey", "").split("-")[0]).strip().upper()
        jira_key = str(work_order.get("jiraKey") or record.get("jiraKey") or "").strip()
        readiness_id = str(record.get("id") or work_order.get("readinessId") or "").strip()
        work_order_id = str(work_order.get("id") or "").strip()
        if not project_key or not jira_key:
            return
        started_at = str(work_order.get("createdAt") or utc_now_iso())
        pm_store.mark_queue_item_in_progress(
            project_key=project_key,
            jira_key=jira_key,
            readiness_id=readiness_id,
            started_at=started_at,
        )
        if work_order_id:
            pm_store.attach_work_order_to_queue_item(
                project_key=project_key,
                jira_key=jira_key,
                work_order_id=work_order_id,
            )

    def dismiss(self, record_id: str, *, actor: str = "human") -> dict[str, Any]:
        record = self.get_record(record_id)
        if not record:
            raise LookupError("Readiness record not found")

        now = utc_now_iso()
        with connect() as conn:
            conn.execute(
                """
                UPDATE readiness_records
                SET readiness_status = 'dismissed', updated_at = ?
                WHERE id = ?
                """,
                (now, record_id),
            )
            self.events.append(
                event_type="READINESS_DISMISSED",
                readiness_id=record_id,
                actor=actor,
                payload={"jiraKey": record["jiraKey"]},
                conn=conn,
            )
        updated = self.get_record(record_id)
        if not updated:
            raise RuntimeError("Failed to dismiss readiness record")
        return updated

    def reanalyze(self, record_id: str, *, actor: str = "human") -> dict[str, Any]:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM readiness_records WHERE id = ?",
                (record_id,),
            ).fetchone()
            if not row:
                raise LookupError("Readiness record not found")
            if row["readiness_status"] in {"promoted", "dismissed"}:
                raise ValueError("Promoted or dismissed records cannot be re-analyzed")

            stored_snapshot = json_loads(row["jira_snapshot_json"], {})
            if not stored_snapshot:
                raise ValueError("Readiness record has no Jira snapshot to analyze")

            snapshot, refreshed_from_jira = self._resolve_reanalyze_snapshot(
                row["jira_key"],
                stored_snapshot,
            )
            analysis_snapshot = {**snapshot, "reanalyzeContext": True}

            self.events.append(
                event_type="READINESS_ANALYSIS_STARTED",
                readiness_id=record_id,
                actor=actor,
                payload={
                    "jiraKey": row["jira_key"],
                    "reanalyze": True,
                    "refreshedFromJira": refreshed_from_jira,
                },
                conn=conn,
            )

            analysis = self._run_analysis(analysis_snapshot, row["project_key"])
            persist_snapshot = dict(analysis.get("jiraSnapshot") or snapshot)
            persist_snapshot.pop("reanalyzeContext", None)

            now = utc_now_iso()
            conn.execute(
                """
                UPDATE readiness_records SET
                    readiness_score = ?,
                    readiness_status = ?,
                    analysis_summary = ?,
                    blockers_json = ?,
                    recommended_repos_json = ?,
                    confidence = ?,
                    estimated_days = ?,
                    jira_snapshot_json = ?,
                    analyzed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    analysis["readinessScore"],
                    analysis["readinessStatus"],
                    analysis["analysisSummary"],
                    json_dumps(analysis["blockers"]),
                    json_dumps(analysis["recommendedRepos"]),
                    analysis["confidence"],
                    analysis.get("estimatedDays"),
                    json_dumps(persist_snapshot),
                    now,
                    now,
                    record_id,
                ),
            )
            self.events.append(
                event_type="READINESS_ANALYSIS_COMPLETED",
                readiness_id=record_id,
                actor=actor,
                payload={
                    "readinessScore": analysis["readinessScore"],
                    "readinessStatus": analysis["readinessStatus"],
                    "reanalyze": True,
                    "refreshedFromJira": refreshed_from_jira,
                    "commentCount": persist_snapshot.get("commentCount", 0),
                },
                conn=conn,
            )

        updated = self.get_record(record_id)
        if not updated:
            raise RuntimeError("Failed to re-analyze readiness record")
        return updated

    def _resolve_reanalyze_snapshot(
        self,
        jira_key: str,
        stored_snapshot: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        if not self._issue_refresher:
            return stored_snapshot, False
        try:
            return self._issue_refresher(jira_key), True
        except ReadinessIntegrationError:
            return stored_snapshot, False

    def _run_analysis(self, snapshot: dict[str, Any], project_key: str) -> dict[str, Any]:
        if self._analysis_runner:
            return self._analysis_runner(snapshot, project_key)
        return analyze_ticket_snapshot(snapshot)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "jiraKey": row["jira_key"],
            "projectKey": row["project_key"],
            "title": row["title"],
            "readinessScore": row["readiness_score"],
            "readinessStatus": row["readiness_status"],
            "analysisSummary": row["analysis_summary"],
            "blockers": json_loads(row["blockers_json"], []),
            "recommendedRepos": json_loads(row["recommended_repos_json"], []),
            "confidence": row["confidence"],
            "estimatedDays": row["estimated_days"],
            "jiraSnapshot": json_loads(row["jira_snapshot_json"], {}),
            "analyzedAt": row["analyzed_at"],
            "promotedWorkOrderId": row["promoted_work_order_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
