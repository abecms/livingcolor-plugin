"""Jira polling and readiness record upserts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from delivery_runtime.events.store import EventStore
from delivery_runtime.persistence.db import connect, json_dumps, json_loads, next_public_id, utc_now_iso
from delivery_runtime.readiness.analyzer import analyze_ticket_snapshot
from delivery_runtime.readiness.errors import ReadinessIntegrationError
from delivery_runtime.readiness.ticket_scope import load_ticket_scope_for_project, matches_ticket_scope


@dataclass(frozen=True)
class ReadinessScanResult:
    project_key: str
    scanned: int
    created: int
    updated: int
    skipped: int
    skipped_out_of_scope: int = 0
    skipped_excluded: int = 0
    dismissed_out_of_scope: int = 0

    @property
    def in_scope(self) -> int:
        return self.created + self.updated

    @property
    def fetched(self) -> int:
        return self.scanned


class ReadinessScanner:
    def __init__(
        self,
        events: EventStore | None = None,
        *,
        issue_fetcher: Callable[[str], list[dict[str, Any]]] | None = None,
        analysis_runner: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
    ) -> None:
        self.events = events or EventStore()
        self._issue_fetcher = issue_fetcher
        self._analysis_runner = analysis_runner or (
            lambda snapshot, project_key: analyze_ticket_snapshot(snapshot)
        )

    def scan_project(self, project_key: str) -> ReadinessScanResult:
        project_key = project_key.strip().upper()
        if not project_key:
            raise ValueError("project_key is required")
        if self._issue_fetcher is None:
            raise ReadinessIntegrationError("Jira integration is not configured on this server")

        self.events.append(
            event_type="READINESS_SCAN_STARTED",
            payload={"projectKey": project_key},
        )

        snapshots = self._issue_fetcher(project_key)
        excluded_keys = self._excluded_jira_keys()
        ticket_scope = load_ticket_scope_for_project(project_key)

        created = updated = skipped = 0
        skipped_out_of_scope = 0
        skipped_excluded = 0
        with connect() as conn:
            for snapshot in snapshots:
                jira_key = str(snapshot.get("key") or "").strip()
                if not jira_key:
                    skipped += 1
                    continue
                if jira_key in excluded_keys:
                    skipped += 1
                    skipped_excluded += 1
                    continue
                if not matches_ticket_scope(snapshot, ticket_scope):
                    skipped += 1
                    skipped_out_of_scope += 1
                    continue

                analysis = self._analysis_runner(snapshot, project_key)
                record_id, was_created = self._upsert_record(
                    conn,
                    jira_key=jira_key,
                    project_key=project_key,
                    analysis=analysis,
                )
                if was_created:
                    created += 1
                    self.events.append(
                        event_type="READINESS_RECORD_CREATED",
                        readiness_id=record_id,
                        payload={"jiraKey": jira_key, "projectKey": project_key},
                        conn=conn,
                    )
                else:
                    updated += 1

                self.events.append(
                    event_type="READINESS_ANALYSIS_COMPLETED",
                    readiness_id=record_id,
                    payload={
                        "jiraKey": jira_key,
                        "readinessScore": analysis["readinessScore"],
                        "readinessStatus": analysis["readinessStatus"],
                    },
                    conn=conn,
                )
                self.events.append(
                    event_type="READINESS_SCORE_UPDATED",
                    readiness_id=record_id,
                    payload={"readinessScore": analysis["readinessScore"]},
                    conn=conn,
                )

            dismissed = self._dismiss_out_of_scope_records(
                conn,
                project_key=project_key,
                ticket_scope=ticket_scope,
            )
            skipped += dismissed

        return ReadinessScanResult(
            project_key=project_key,
            scanned=len(snapshots),
            created=created,
            updated=updated,
            skipped=skipped,
            skipped_out_of_scope=skipped_out_of_scope,
            skipped_excluded=skipped_excluded,
            dismissed_out_of_scope=dismissed,
        )

    @staticmethod
    def _dismiss_out_of_scope_records(conn, *, project_key: str, ticket_scope) -> int:
        rows = conn.execute(
            """
            SELECT id, jira_snapshot_json FROM readiness_records
            WHERE project_key = ? AND readiness_status NOT IN ('promoted', 'dismissed')
            """,
            (project_key,),
        ).fetchall()
        now = utc_now_iso()
        dismissed = 0
        for row in rows:
            snapshot = json_loads(row["jira_snapshot_json"], {})
            if not isinstance(snapshot, dict):
                snapshot = {}
            if matches_ticket_scope(snapshot, ticket_scope):
                continue
            conn.execute(
                """
                UPDATE readiness_records
                SET readiness_status = 'dismissed', updated_at = ?
                WHERE id = ?
                """,
                (now, row["id"]),
            )
            dismissed += 1
        return dismissed

    @staticmethod
    def _excluded_jira_keys() -> set[str]:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT jira_key FROM readiness_records WHERE readiness_status = 'promoted'
                UNION
                SELECT jira_key FROM work_orders
                WHERE status NOT IN ('completed', 'cancelled', 'failed')
                """
            ).fetchall()
        return {str(row["jira_key"]) for row in rows}

    @staticmethod
    def _upsert_record(
        conn,
        *,
        jira_key: str,
        project_key: str,
        analysis: dict[str, Any],
    ) -> tuple[str, bool]:
        now = utc_now_iso()
        existing = conn.execute(
            """
            SELECT id FROM readiness_records
            WHERE jira_key = ? AND readiness_status NOT IN ('promoted', 'dismissed')
            """,
            (jira_key,),
        ).fetchone()

        snapshot = analysis["jiraSnapshot"]
        title = str(snapshot.get("summary") or snapshot.get("title") or jira_key)

        if existing:
            record_id = existing["id"]
            conn.execute(
                """
                UPDATE readiness_records SET
                    project_key = ?,
                    title = ?,
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
                    project_key,
                    title,
                    analysis["readinessScore"],
                    analysis["readinessStatus"],
                    analysis["analysisSummary"],
                    json_dumps(analysis["blockers"]),
                    json_dumps(analysis["recommendedRepos"]),
                    analysis["confidence"],
                    analysis.get("estimatedDays"),
                    json_dumps(snapshot),
                    now,
                    now,
                    record_id,
                ),
            )
            return record_id, False

        record_id = next_public_id(conn, "RD")
        conn.execute(
            """
            INSERT INTO readiness_records (
                id, jira_key, project_key, title, readiness_score, readiness_status,
                analysis_summary, blockers_json, recommended_repos_json, confidence,
                estimated_days, jira_snapshot_json, analyzed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                jira_key,
                project_key,
                title,
                analysis["readinessScore"],
                analysis["readinessStatus"],
                analysis["analysisSummary"],
                json_dumps(analysis["blockers"]),
                json_dumps(analysis["recommendedRepos"]),
                analysis["confidence"],
                analysis.get("estimatedDays"),
                json_dumps(snapshot),
                now,
                now,
                now,
            ),
        )
        return record_id, True
