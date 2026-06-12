"""Tests for automatic execution queue consumption."""

from __future__ import annotations

import pytest

from delivery_runtime.events.store import EventStore
from delivery_runtime.persistence.db import connect, init_db, json_dumps, next_public_id, utc_now_iso
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.pm_inbox.queue_consumer import ExecutionQueueConsumer
from delivery_runtime.readiness.service import ReadinessService
from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping
from delivery_runtime.work_orders.service import WorkOrderService


class _StubOrchestrator:
    def __init__(self) -> None:
        self.ticked: list[str] = []

    def tick(self, work_order_id: str) -> list[str]:
        self.ticked.append(work_order_id)
        return [work_order_id]


def _seed_ready_record(conn, *, jira_key: str = "AAC-700", project_key: str = "AAC") -> str:
    record_id = next_public_id(conn, "RD")
    now = utc_now_iso()
    snapshot = {
        "key": jira_key,
        "summary": "OAuth callback",
        "description": (
            "Acceptance criteria:\n"
            "- Given a signed-in user\n"
            "- When OAuth completes on https://example.com/callback\n"
            "- Then store the token\n"
            "Steps to reproduce: open /login and complete OAuth."
        ),
        "status": "To Do",
        "issueType": "Story",
        "projectKey": project_key,
        "priority": "High",
    }
    conn.execute(
        """
        INSERT INTO readiness_records (
            id, jira_key, project_key, title, readiness_score, readiness_status,
            analysis_summary, blockers_json, recommended_repos_json, confidence,
            jira_snapshot_json, analyzed_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 90, 'ready', 'Ready', '[]', ?, 0.9, ?, ?, ?, ?)
        """,
        (
            record_id,
            jira_key,
            project_key,
            snapshot["summary"],
            json_dumps(["gitlab.com/org/app"]),
            json_dumps(snapshot),
            now,
            now,
            now,
        ),
    )
    return record_id


def _seed_queue_item(conn, *, readiness_id: str, jira_key: str, project_key: str = "AAC") -> None:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO execution_queue_items (
            id, project_key, readiness_id, jira_key, title, queue_status,
            priority_score, estimated_days, complexity, confidence,
            blockers_json, priority_factors_json, position, recommended_next,
            run_id, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'executable', 92, 1.5, 'Medium', 0.82, '[]', '{}', 1, 1, 'DA-1', ?)
        """,
        (next_public_id(conn, "EQ"), project_key, readiness_id, jira_key, "OAuth callback", now),
    )


class TestExecutionQueueConsumer:
    @pytest.fixture(autouse=True)
    def _setup(self, _isolate_hermes_home):
        install_phase25_project_mapping()
        init_db()

    def test_auto_starts_work_order_from_queue_item_one(self):
        with connect() as conn:
            readiness_id = _seed_ready_record(conn)
            _seed_queue_item(conn, readiness_id=readiness_id, jira_key="AAC-700")

        events = EventStore()
        orchestrator = _StubOrchestrator()
        readiness = ReadinessService(events=events, work_orders=WorkOrderService(events))
        consumer = ExecutionQueueConsumer(
            events=events,
            work_orders=readiness.work_orders,
            readiness=readiness,
            orchestrator=orchestrator,
        )

        result = consumer.try_consume("AAC")
        assert result["started"] is True
        assert result["jiraKey"] == "AAC-700"
        assert orchestrator.ticked

        active = consumer.get_active_development("AAC")
        assert active is not None
        assert active["jiraKey"] == "AAC-700"

    def test_skips_when_active_development_exists(self):
        with connect() as conn:
            readiness_id = _seed_ready_record(conn, jira_key="AAC-701")
            _seed_queue_item(conn, readiness_id=readiness_id, jira_key="AAC-701")
            now = utc_now_iso()
            conn.execute(
                """
                INSERT INTO work_orders (
                    id, jira_key, readiness_id, title, description, priority,
                    status, current_stage, confidence, created_at, updated_at
                ) VALUES ('WO-1', 'AAC-800', ?, 'Active', '', 'High', 'running', 'development', 0.8, ?, ?)
                """,
                (readiness_id, now, now),
            )

        consumer = ExecutionQueueConsumer(
            events=EventStore(),
            work_orders=WorkOrderService(EventStore()),
            readiness=ReadinessService(events=EventStore(), work_orders=WorkOrderService(EventStore())),
            orchestrator=_StubOrchestrator(),
        )
        result = consumer.try_consume("AAC")
        assert result["started"] is False
        assert result["reason"] == "active_development_exists"

    def test_failure_releases_ticket_back_to_queue(self):
        with connect() as conn:
            readiness_id = _seed_ready_record(conn, jira_key="AAC-702")
            _seed_queue_item(conn, readiness_id=readiness_id, jira_key="AAC-702")

        pm_store.mark_queue_item_in_progress(
            project_key="AAC",
            jira_key="AAC-702",
            readiness_id=readiness_id,
            started_at=utc_now_iso(),
        )

        consumer = ExecutionQueueConsumer(events=EventStore())
        consumer.handle_development_failure(
            project_key="AAC",
            jira_key="AAC-702",
            readiness_id=readiness_id,
            work_order_id="WO-9",
            reason="development failed",
        )

        queue = pm_store.get_execution_queue(project_key="AAC")
        item = next(row for row in queue["items"] if row["jiraKey"] == "AAC-702")
        assert item["queueStatus"] == "executable"
        assert item["failureReason"] == "development failed"
