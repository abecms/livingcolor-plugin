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

    def test_schema_faq_page_ticket_is_not_marked_non_development(self):
        snapshot = {
            "key": "TVP-2391",
            "summary": 'Ajout de données structurées sur les pages de catégories "FILMS"',
            "description": (
                'Sections "FAQ" SEO avec "@type": "FAQPage" et url https://example.com/fr/films#faq'
            ),
            "status": "À FAIRE",
            "issueType": "Task",
            "projectKey": "TVP",
        }
        analysis = analyze_for_daily_delivery(snapshot)
        assert analysis["readinessStatus"] != "not_development"

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

        def _llm_like_analysis_runner(snapshot: dict, project_key: str) -> dict:
            item = {**snapshot, "projectKey": project_key.strip().upper()}
            result = analyze_for_daily_delivery(item)
            if "jiraSnapshot" not in result:
                result = {**result, "jiraSnapshot": item}
            return result

        scanner = ReadinessScanner(
            issue_fetcher=lambda _project: snapshots,
            analysis_runner=_llm_like_analysis_runner,
        )
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
        estimations = pm_store.latest_estimations_by_readiness(project_key="AAC")
        assert clarification["record"]["id"] not in estimations
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

    def test_manual_daily_analysis_forces_dispatcher_even_when_cached(self):
        from delivery_runtime.readiness.analysis_dispatcher import AnalysisCacheEntry
        from delivery_runtime.readiness.analyst_backend import SynchronousAnalystBackend
        from delivery_runtime.readiness.scanner import ReadinessScanner

        calls: list[str] = []
        snapshots = [_ready_snapshot("AAC-701")]

        def runner(snapshot: dict, project_key: str) -> dict:
            calls.append(snapshot["key"])
            return {
                "readinessScore": 90,
                "readinessStatus": "ready",
                "analysisSummary": "Fresh LLM result",
                "blockers": [],
                "recommendedRepos": ["group/bn-frontend"],
                "confidence": 0.9,
                "estimatedDays": 1.0,
                "jiraSnapshot": snapshot,
            }

        scanner = ReadinessScanner(
            issue_fetcher=lambda _project: snapshots,
            analysis_backend=SynchronousAnalystBackend(runner),
            cache_lookup=lambda _jira_key: AnalysisCacheEntry(
                jira_key="AAC-701",
                analysis_input_hash="stale",
                analysis=runner(snapshots[0], "AAC"),
            ),
        )
        calls.clear()
        pipeline = DailyAnalysisPipeline(scanner=scanner)

        result = pipeline.run("AAC", force=True)

        assert calls == ["AAC-701"]
        assert result["analysisDispatch"]["forced"] is True
        assert result["analysisDispatch"]["success"] == 1

    def test_automatic_daily_analysis_reuses_cached_result(self):
        from delivery_runtime.readiness.analysis_dispatcher import (
            AnalysisCacheEntry,
            build_analysis_input_hash,
        )
        from delivery_runtime.readiness.analyst_backend import SynchronousAnalystBackend
        from delivery_runtime.readiness.scanner import ReadinessScanner

        calls: list[str] = []
        snapshot = _ready_snapshot("AAC-702")
        cached_analysis = {
            "readinessScore": 88,
            "readinessStatus": "ready",
            "analysisSummary": "Cached LLM result",
            "blockers": [],
            "recommendedRepos": ["group/bn-frontend"],
            "confidence": 0.88,
            "estimatedDays": 1.0,
            "jiraSnapshot": snapshot,
        }
        input_hash = build_analysis_input_hash(snapshot, project_key="AAC")

        def runner(snapshot: dict, project_key: str) -> dict:
            calls.append(snapshot["key"])
            return cached_analysis

        scanner = ReadinessScanner(
            issue_fetcher=lambda _project: [snapshot],
            analysis_backend=SynchronousAnalystBackend(runner),
            cache_lookup=lambda _jira_key: AnalysisCacheEntry(
                jira_key="AAC-702",
                analysis_input_hash=input_hash,
                analysis=cached_analysis,
            ),
        )
        pipeline = DailyAnalysisPipeline(scanner=scanner)

        result = pipeline.run("AAC", force=False)

        assert calls == []
        assert result["analysisDispatch"]["cached"] == 1
        assert result["analysisDispatch"]["success"] == 0

    def test_pm_inbox_includes_latest_analysis_dispatch(self):
        dispatch = {
            "backend": "hermes_subagent",
            "concurrency": 3,
            "success": 2,
            "cached": 1,
            "failed": 1,
            "skipped": 0,
            "forced": True,
            "durationMs": 1234,
            "items": [
                {
                    "jiraKey": "AAC-901",
                    "status": "failed",
                    "backend": "hermes_subagent",
                    "durationMs": 250,
                    "error": "subagent timeout",
                }
            ],
        }
        with connect() as conn:
            run_id = pm_store.create_daily_run(conn, project_key="AAC")
            pm_store.complete_daily_run(
                conn,
                run_id=run_id,
                status="completed",
                jira_synced=4,
                analyzed=2,
                estimated=1,
                pipeline={
                    "scan": {"scanned": 4, "inScope": 4},
                    "analysisDispatch": dispatch,
                },
            )

        inbox = build_pm_inbox(project_key="AAC")

        assert inbox["lastRun"]["status"] == "completed"
        assert inbox["analysisDispatch"] == dispatch

    def test_failed_analysis_preserves_previous_readiness_record(self):
        from delivery_runtime.api.schemas import PmInboxResponse
        from delivery_runtime.readiness.analyst_backend import SynchronousAnalystBackend
        from delivery_runtime.readiness.scanner import ReadinessScanner

        snapshot = _ready_snapshot("AAC-801")
        with connect() as conn:
            now = utc_now_iso()
            conn.execute(
                """
                INSERT INTO readiness_records (
                    id, jira_key, project_key, title, readiness_score, readiness_status,
                    analysis_summary, blockers_json, recommended_repos_json, confidence,
                    estimated_days, jira_snapshot_json, analyzed_at, created_at, updated_at
                ) VALUES ('RD-801', 'AAC-801', 'AAC', 'Previous ready', 88, 'ready',
                          'Previous LLM result', '[]', '["group/bn-frontend"]', 0.88,
                          1.0, ?, ?, ?, ?)
                """,
                (json_dumps(snapshot), now, now, now),
            )

        def failing_runner(snapshot: dict, project_key: str) -> dict:
            raise RuntimeError("subagent timeout")

        scanner = ReadinessScanner(
            issue_fetcher=lambda _project: [snapshot],
            analysis_backend=SynchronousAnalystBackend(failing_runner),
        )
        pipeline = DailyAnalysisPipeline(scanner=scanner)
        result = pipeline.run("AAC", force=True)

        assert result["analysisDispatch"]["failed"] == 1
        with connect() as conn:
            row = conn.execute(
                "SELECT readiness_status, last_analysis_error FROM readiness_records WHERE jira_key = 'AAC-801'"
            ).fetchone()
        assert row["readiness_status"] == "ready"
        assert "subagent timeout" in row["last_analysis_error"]

        inbox = build_pm_inbox(project_key="AAC")
        inbox = PmInboxResponse.model_validate(inbox).model_dump()
        sprint_ticket = next(
            ticket for ticket in inbox["selectedSprint"]["tickets"] if ticket["jiraKey"] == "AAC-801"
        )
        assert sprint_ticket["readinessStatus"] == "ready"
        assert sprint_ticket["lastAnalysisError"] == "subagent timeout"
        assert sprint_ticket["lastAnalysisFailedAt"]
        assert "Latest LLM analysis failed; review the error before promotion" in sprint_ticket["warnings"]

    def test_failed_analysis_without_previous_record_creates_analysis_failed(self):
        from delivery_runtime.readiness.analyst_backend import SynchronousAnalystBackend
        from delivery_runtime.readiness.scanner import ReadinessScanner

        snapshot = _ready_snapshot("AAC-802")

        def failing_runner(snapshot: dict, project_key: str) -> dict:
            raise RuntimeError("subagent timeout")

        scanner = ReadinessScanner(
            issue_fetcher=lambda _project: [snapshot],
            analysis_backend=SynchronousAnalystBackend(failing_runner),
        )
        pipeline = DailyAnalysisPipeline(scanner=scanner)
        result = pipeline.run("AAC", force=True)

        assert result["analysisDispatch"]["failed"] == 1
        with connect() as conn:
            row = conn.execute(
                "SELECT readiness_status, last_analysis_error FROM readiness_records WHERE jira_key = 'AAC-802'"
            ).fetchone()
        assert row["readiness_status"] == "analysis_failed"
        assert "subagent timeout" in row["last_analysis_error"]

    def test_automatic_analysis_failed_record_is_not_reused_as_cache(self):
        from delivery_runtime.readiness.analysis_dispatcher import build_analysis_input_hash
        from delivery_runtime.readiness.analyst_backend import SynchronousAnalystBackend
        from delivery_runtime.readiness.scanner import ReadinessScanner

        snapshot = _ready_snapshot("AAC-803")
        input_hash = build_analysis_input_hash(snapshot, project_key="AAC")
        with connect() as conn:
            now = utc_now_iso()
            conn.execute(
                """
                INSERT INTO readiness_records (
                    id, jira_key, project_key, title, readiness_score, readiness_status,
                    analysis_summary, blockers_json, recommended_repos_json, confidence,
                    estimated_days, analysis_input_hash, analysis_backend,
                    last_analysis_error, last_analysis_failed_at,
                    jira_snapshot_json, analyzed_at, created_at, updated_at
                ) VALUES ('RD-803', 'AAC-803', 'AAC', 'Failed analysis', 0, 'analysis_failed',
                          'LLM analysis failed before producing a valid readiness result.',
                          '[]', '[]', 0, NULL, ?, 'hermes_subagent',
                          'previous timeout', ?, ?, NULL, ?, ?)
                """,
                (input_hash, now, json_dumps(snapshot), now, now),
            )

        calls: list[str] = []

        def failing_runner(snapshot: dict, project_key: str) -> dict:
            calls.append(snapshot["key"])
            raise RuntimeError("new timeout")

        scanner = ReadinessScanner(
            issue_fetcher=lambda _project: [snapshot],
            analysis_backend=SynchronousAnalystBackend(failing_runner),
        )
        pipeline = DailyAnalysisPipeline(scanner=scanner)
        result = pipeline.run("AAC", force=False)

        assert calls == ["AAC-803"]
        assert result["analysisDispatch"]["cached"] == 0
        assert result["analysisDispatch"]["failed"] == 1
        with connect() as conn:
            row = conn.execute(
                """
                SELECT readiness_status, last_analysis_error, analysis_input_hash, analysis_backend
                FROM readiness_records WHERE jira_key = 'AAC-803'
                """
            ).fetchone()
        assert row["readiness_status"] == "analysis_failed"
        assert "new timeout" in row["last_analysis_error"]
        assert row["analysis_input_hash"] == input_hash
        assert row["analysis_backend"] == "hermes_conversation"


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
                ) VALUES (?, 'BN-900', 'BN', 'Out of sprint', 10, 'not_development',
                          'Support request', '[]', '[]', 0.9, ?, ?, ?, ?)
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
                ) VALUES (?, ?, NULL, 'BN-900', 'not_development', 'pending', 'Please clarify', ?, ?)
                """,
                (proposal_id, out_of_sprint_record_id, now, now),
            )

        inbox = build_pm_inbox(project_key="BN")
        sprint_keys = {ticket["jiraKey"] for ticket in inbox["selectedSprint"]["tickets"]}
        assert "BN-100" in sprint_keys
        assert "BN-900" not in sprint_keys
        assert not any(item["record"]["jiraKey"] == "BN-900" for item in inbox["needsClarification"])
        assert not any(item["record"]["jiraKey"] == "BN-900" for item in inbox["notReady"])
        assert not any(item["jiraKey"] == "BN-900" for item in inbox["waitingForApproval"])

    def test_inbox_includes_not_ready_sprint_tickets(self):
        with connect() as conn:
            sprint_record_id = next_public_id(conn, "RD")
            now = utc_now_iso()
            sprint_snapshot = json_dumps({"key": "BN-200", "status": "To Do", "statusCategory": "To Do"})
            conn.execute(
                """
                INSERT INTO readiness_records (
                    id, jira_key, project_key, title, readiness_score, readiness_status,
                    analysis_summary, blockers_json, recommended_repos_json, confidence,
                    jira_snapshot_json, analyzed_at, created_at, updated_at
                ) VALUES (?, 'BN-200', 'BN', 'Blocked sprint ticket', 35, 'not_ready',
                          'Blocked', '["Description is too short"]', '[]', 0.4, ?, ?, ?, ?)
                """,
                (sprint_record_id, sprint_snapshot, now, now, now),
            )
            pm_store.insert_estimation(
                conn,
                readiness_id=sprint_record_id,
                jira_key="BN-200",
                complexity="Small",
                estimated_days=1.0,
                confidence=0.4,
                run_id="RUN-TEST",
            )

        inbox = build_pm_inbox(project_key="BN")
        blocked = next(item for item in inbox["notReady"] if item["record"]["jiraKey"] == "BN-200")
        assert blocked["detectedIssues"] == ["Description is too short"]
        assert blocked["proposal"] is None


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
