"""Tests for BN daily delivery analysis and PM Inbox."""

from __future__ import annotations

import pytest

from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.automation.scheduler import run_daily_analysis_if_due, should_run_daily_analysis
from delivery_runtime.persistence.db import SCHEMA_VERSION, connect, init_db, json_dumps, next_public_id, utc_now_iso
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.pm_inbox.analyst import analyze_for_daily_delivery
from delivery_runtime.pm_inbox.daily_pipeline import DailyAnalysisPipeline
from delivery_runtime.pm_inbox.execution_queue import build_execution_queue
from delivery_runtime.pm_inbox.inbox import build_pm_inbox
from delivery_runtime.pm_inbox.priority import compute_priority_score
from delivery_runtime.pm_inbox.service import PmInboxService
from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping


def _ready_snapshot(key: str = "AAC-100") -> dict:
    return {
        "key": key,
        "summary": "Fix OAuth callback redirect",
        "description": (
            "Acceptance criteria:\n"
            "- Given a signed-in user\n"
            "- When OAuth completes on https://example.com/callback\n"
            "- Then store the token\n"
            "Steps to reproduce: open /login and complete OAuth."
        ),
        "status": "To Do",
        "issueType": "Story",
        "projectKey": "AAC",
        "priority": "High",
    }


def _support_snapshot(key: str = "AAC-200") -> dict:
    return {
        "key": key,
        "summary": "Update homepage copy",
        "description": "Please adjust editorial wording on the homepage hero.",
        "status": "To Do",
        "issueType": "Request",
        "projectKey": "AAC",
    }


def _thin_snapshot(key: str = "AAC-300") -> dict:
    return {
        "key": key,
        "summary": "Broken page",
        "description": "It fails.",
        "status": "To Do",
        "issueType": "Bug",
        "projectKey": "AAC",
    }


class TestDailyAnalyst:
    @pytest.fixture(autouse=True)
    def _setup(self, _isolate_hermes_home):
        install_phase25_project_mapping()

    def test_ready_ticket_is_actionable(self):
        analysis = analyze_for_daily_delivery(_ready_snapshot())
        assert analysis["readinessStatus"] == "ready"
        assert analysis["actionable"] is True
        assert analysis["proposedComment"] == ""

    def test_support_ticket_is_not_development(self):
        analysis = analyze_for_daily_delivery(_support_snapshot())
        assert analysis["readinessStatus"] == "not_development"
        assert analysis["proposalType"] == "not_development"
        assert analysis["proposedComment"]

    def test_thin_ticket_needs_clarification(self):
        analysis = analyze_for_daily_delivery(_thin_snapshot())
        assert analysis["readinessStatus"] == "needs_clarification"
        assert analysis["proposalType"] == "needs_clarification"
        assert "étapes de reproduction" in analysis["proposedComment"].lower()

    def test_priority_score_orders_executable_ticket(self):
        score = compute_priority_score(
            snapshot=_ready_snapshot(),
            readiness_score=90,
            estimated_days=1.5,
            confidence=0.82,
            readiness_status="ready",
            blockers=[],
        )
        assert score.score >= 70


class TestExecutionQueue:
    @pytest.fixture(autouse=True)
    def _setup(self, _isolate_hermes_home):
        install_phase25_project_mapping()

    def test_queue_places_executable_tickets_first(self):
        tickets = [
            {
                "readinessId": "RD-1",
                "jiraKey": "AAC-1",
                "title": "Ready ticket",
                "readinessStatus": "ready",
                "readinessScore": 90,
                "blockers": [],
                "jiraSnapshot": _ready_snapshot("AAC-1"),
                "estimation": {"estimatedDays": 1.5, "complexity": "Medium", "confidence": 0.8},
            },
            {
                "readinessId": "RD-2",
                "jiraKey": "AAC-2",
                "title": "Blocked ticket",
                "readinessStatus": "needs_clarification",
                "readinessScore": 40,
                "blockers": ["Missing info"],
                "jiraSnapshot": _thin_snapshot("AAC-2"),
                "estimation": None,
            },
        ]
        snapshot = build_execution_queue(project_key="AAC", tickets=tickets)
        assert snapshot.items[0].queue_status == "executable"
        assert snapshot.recommended_next is not None
        assert snapshot.recommended_next.jira_key == snapshot.items[0].jira_key


class TestDailyPipeline:
    @pytest.fixture(autouse=True)
    def _setup(self, _isolate_hermes_home):
        install_phase25_project_mapping()
        init_db()

    def test_pipeline_persists_estimations_and_inbox(self):
        snapshots = [_ready_snapshot("AAC-501"), _thin_snapshot("AAC-502"), _support_snapshot("AAC-503")]

        from delivery_runtime.readiness.scanner import ReadinessScanner

        scanner = ReadinessScanner(issue_fetcher=lambda _project: snapshots)
        pipeline = DailyAnalysisPipeline(scanner=scanner)
        result = pipeline.run("AAC")

        assert result["scan"]["scanned"] == 3
        assert result["qualification"]["analyzed"] == 3
        assert result["qualification"]["estimated"] == 1
        assert result["executionQueue"]["items"]
        assert result["executionQueue"]["executableCount"] >= 1
        assert result["selectedSprint"]["capacityDays"] > 0
        assert result["selectedSprint"]["tickets"]
        assert result["projectMemory"]["highlights"] is not None

        inbox = build_pm_inbox(project_key="AAC")
        assert inbox["projectKey"] == "AAC"
        assert inbox["lastRun"]["status"] == "completed"
        sprint_keys = {ticket["jiraKey"] for ticket in inbox["selectedSprint"]["tickets"]}
        assert "AAC-501" in sprint_keys
        assert all(item["jiraKey"] in sprint_keys for item in inbox["waitingForApproval"])
        assert all(item["jiraKey"] in sprint_keys for item in inbox["activeDevelopments"])
        clarification = next(item for item in inbox["needsClarification"] if item["record"]["jiraKey"] == "AAC-502")
        assert clarification["proposal"] is not None
        assert clarification["proposal"]["proposalType"] == "needs_clarification"
        assert inbox["executionQueue"]["items"]
        assert all(item["jiraKey"] in sprint_keys for item in inbox["executionQueue"]["items"])
        assert inbox["selectedSprint"]["tickets"]
        assert inbox["recommendedNext"] is not None or inbox["executionQueue"]["executableCount"] == 0

        with connect() as conn:
            version = conn.execute(
                "SELECT value FROM delivery_meta WHERE key = 'schema_version'"
            ).fetchone()
        assert int(version["value"]) == SCHEMA_VERSION

    def test_pipeline_ignores_non_todo_tickets(self):
        snapshots = [
            _ready_snapshot("AAC-601"),
            {**_ready_snapshot("AAC-602"), "status": "In Progress", "statusCategory": "In Progress"},
        ]

        from delivery_runtime.readiness.scanner import ReadinessScanner

        scanner = ReadinessScanner(issue_fetcher=lambda _project: snapshots)
        pipeline = DailyAnalysisPipeline(scanner=scanner)
        result = pipeline.run("AAC")

        assert result["scan"]["scanned"] == 2
        assert result["scan"]["skipped"] == 1
        assert result["qualification"]["analyzed"] == 1
        assert result["qualification"]["estimated"] == 1
        assert {ticket["jiraKey"] for ticket in result["selectedSprint"]["tickets"]} == {"AAC-601"}


class TestPmInboxService:
    @pytest.fixture(autouse=True)
    def _setup(self, _isolate_hermes_home):
        init_db()

    def test_comment_proposal_decision_flow(self):
        with connect() as conn:
            record_id = next_public_id(conn, "RD")
            now = utc_now_iso()
            conn.execute(
                """
                INSERT INTO readiness_records (
                    id, jira_key, project_key, title, readiness_score, readiness_status,
                    analysis_summary, blockers_json, recommended_repos_json, confidence,
                    jira_snapshot_json, analyzed_at, created_at, updated_at
                ) VALUES (?, 'BN-900', 'BN', 'Thin bug', 40, 'needs_clarification',
                          'Needs info', '[]', '[]', 0.4, '{}', ?, ?, ?)
                """,
                (record_id, now, now, now),
            )
            proposal_id = next_public_id(conn, "JP")
            conn.execute(
                """
                INSERT INTO jira_comment_proposals (
                    id, readiness_id, work_order_id, jira_key, proposal_type, status,
                    body, created_at, updated_at
                ) VALUES (?, ?, NULL, 'BN-900', 'needs_clarification', 'pending', 'Please clarify', ?, ?)
                """,
                (proposal_id, record_id, now, now),
            )

        service = PmInboxService()
        approved = service.decide_comment_proposal(proposal_id, action="approve")
        assert approved["status"] == "approved"

    def test_inbox_review_sections_exclude_out_of_sprint_tickets(self):
        with connect() as conn:
            sprint_record_id = next_public_id(conn, "RD")
            out_of_sprint_record_id = next_public_id(conn, "RD")
            now = utc_now_iso()
            sprint_snapshot = json_dumps({"key": "BN-100", "status": "To Do", "statusCategory": "To Do"})
            out_of_sprint_snapshot = json_dumps({"key": "BN-900", "status": "To Do", "statusCategory": "To Do"})
            conn.execute(
                """
                INSERT INTO readiness_records (
                    id, jira_key, project_key, title, readiness_score, readiness_status,
                    analysis_summary, blockers_json, recommended_repos_json, confidence,
                    jira_snapshot_json, analyzed_at, created_at, updated_at
                ) VALUES (?, 'BN-100', 'BN', 'Sprint ticket', 90, 'ready',
                          'Ready', '[]', '[]', 0.9, ?, ?, ?, ?)
                """,
                (sprint_record_id, sprint_snapshot, now, now, now),
            )
            conn.execute(
                """
                INSERT INTO readiness_records (
                    id, jira_key, project_key, title, readiness_score, readiness_status,
                    analysis_summary, blockers_json, recommended_repos_json, confidence,
                    jira_snapshot_json, analyzed_at, created_at, updated_at
                ) VALUES (?, 'BN-900', 'BN', 'Out of sprint', 40, 'needs_clarification',
                          'Needs info', '[]', '[]', 0.4, ?, ?, ?, ?)
                """,
                (out_of_sprint_record_id, out_of_sprint_snapshot, now, now, now),
            )
            pm_store.insert_estimation(
                conn,
                readiness_id=sprint_record_id,
                jira_key="BN-100",
                complexity="Small",
                estimated_days=1.0,
                confidence=0.9,
                run_id="RUN-TEST",
            )
            proposal_id = next_public_id(conn, "JP")
            conn.execute(
                """
                INSERT INTO jira_comment_proposals (
                    id, readiness_id, work_order_id, jira_key, proposal_type, status,
                    body, created_at, updated_at
                ) VALUES (?, ?, NULL, 'BN-900', 'needs_clarification', 'pending', 'Please clarify', ?, ?)
                """,
                (proposal_id, out_of_sprint_record_id, now, now),
            )

        inbox = build_pm_inbox(project_key="BN")
        sprint_keys = {ticket["jiraKey"] for ticket in inbox["selectedSprint"]["tickets"]}
        assert "BN-100" in sprint_keys
        assert "BN-900" not in sprint_keys
        clarification = next(item for item in inbox["needsClarification"] if item["record"]["jiraKey"] == "BN-900")
        assert clarification["proposal"] is not None
        assert not any(item["jiraKey"] == "BN-900" for item in inbox["waitingForApproval"])


class TestDailyScheduler:
    def test_default_config_is_bn_noon(self, monkeypatch):
        monkeypatch.delenv("LIVINGCOLOR_PROJECT_KEY", raising=False)
        config = load_delivery_automation_config()
        assert config.project_key == "BN"
        assert config.daily_analysis_cron.hour == 12
        assert config.daily_analysis_cron.minute == 0

    def test_scheduler_runs_once_per_slot(self):
        from datetime import UTC, datetime

        calls: list[str] = []

        def runner() -> None:
            calls.append("ran")

        now = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
        assert should_run_daily_analysis(now)
        assert run_daily_analysis_if_due(runner, now=now, force=True)
        assert run_daily_analysis_if_due(runner, now=now, force=True) is False
        assert calls == ["ran"]
