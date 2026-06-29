"""Tests for sprint retrospective publishing."""

from __future__ import annotations

from datetime import UTC, datetime

from delivery_runtime.automation.config import save_delivery_project_config
from delivery_runtime.persistence.db import connect, utc_now_iso
from delivery_runtime.pm_inbox.sprint_report import (
    build_sprint_report_snapshot,
    publish_sprint_report,
    should_run_scheduled_sprint_report,
    sprint_report_dedup_key,
)
from delivery_runtime.pm_inbox.sprint_selection import persist_selected_sprint


def _seed_sprint_state(*, project_key: str, sprint_number: int, end_date: str) -> None:
    payload = {
        "sprintName": f"Sprint {sprint_number}",
        "capacityDays": 15.0,
        "usedDays": 5.0,
        "durationDays": 14,
        "overflowRisk": False,
        "warnings": [],
        "tickets": [
            {
                "readinessId": "RD-BN-1",
                "jiraKey": "BN-1",
                "title": "First ticket",
                "estimatedDays": 2.0,
                "priorityRank": 1,
                "urgencyScore": 1.0,
                "warnings": [],
            }
        ],
    }
    persist_selected_sprint(
        project_key=project_key,
        payload=payload,
        memory_patch={
            "sprintNumber": sprint_number,
            "sprintStartDate": "2026-06-03",
            "sprintEndDate": end_date,
        },
    )


def test_build_sprint_report_snapshot_includes_work_orders(_isolate_hermes_home):
    project_key = "BN"
    save_delivery_project_config(duration_days=14, capacity_days=15, project_key=project_key)
    _seed_sprint_state(project_key=project_key, sprint_number=3, end_date="2026-06-16")

    now = utc_now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO work_orders (
                id, jira_key, readiness_id, title, description, priority, status,
                current_stage, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("WO-1", "BN-1", "RD-BN-1", "First ticket", "", "High", "completed", "done", 0.9, now, now),
        )

    snapshot = build_sprint_report_snapshot(project_key=project_key)
    assert snapshot is not None
    assert snapshot["sprintNumber"] == 3
    assert snapshot["ticketsPlanned"][0]["jiraKey"] == "BN-1"
    assert snapshot["workOrderStatusCounts"]["completed"] == 1
    assert snapshot["doneTicketKeys"] == ["BN-1"]
    assert snapshot["deliveredTicketKeys"] == ["BN-1"]


def test_publish_sprint_report_sends_and_deduplicates(_isolate_hermes_home):
    project_key = "BN"
    save_delivery_project_config(duration_days=14, capacity_days=15, project_key=project_key)
    _seed_sprint_state(project_key=project_key, sprint_number=2, end_date="2026-06-16")

    sent_messages: list[str] = []

    def fake_compose(snapshot, key):
        assert key == project_key
        return f"Sprint report for {snapshot['sprint']['name']}"

    def fake_send(message: str):
        sent_messages.append(message)
        return {"success": True, "platform": "slack"}

    first = publish_sprint_report(
        project_key=project_key,
        reporter=fake_compose,
        sender=fake_send,
    )
    assert first["status"] == "sent"
    assert sent_messages == ["Sprint report for Sprint 2"]

    second = publish_sprint_report(
        project_key=project_key,
        reporter=fake_compose,
        sender=fake_send,
    )
    assert second["status"] == "skipped"
    assert second["reason"] == "already_published"
    assert len(sent_messages) == 1


def test_should_run_scheduled_sprint_report_on_end_day(_isolate_hermes_home):
    project_key = "BN"
    save_delivery_project_config(duration_days=14, capacity_days=15, project_key=project_key)
    _seed_sprint_state(project_key=project_key, sprint_number=1, end_date="2026-06-16")

    end_day = datetime(2026, 6, 16, 16, 0, tzinfo=UTC)
    assert should_run_scheduled_sprint_report(project_key=project_key, now=end_day) is True

    wrong_day = datetime(2026, 6, 15, 16, 0, tzinfo=UTC)
    assert should_run_scheduled_sprint_report(project_key=project_key, now=wrong_day) is False


def test_sprint_report_dedup_key_is_stable():
    assert sprint_report_dedup_key(sprint_number=4, sprint_end_date="2026-06-16") == "4:2026-06-16"


def test_build_sprint_report_snapshot_excludes_in_progress_from_done_keys(_isolate_hermes_home):
    project_key = "BN"
    save_delivery_project_config(duration_days=14, capacity_days=15, project_key=project_key)
    payload = {
        "sprintName": "Sprint 3",
        "capacityDays": 15.0,
        "usedDays": 8.0,
        "durationDays": 14,
        "overflowRisk": False,
        "warnings": [],
        "tickets": [
            {
                "readinessId": "RD-BN-1",
                "jiraKey": "BN-1",
                "title": "Done ticket",
                "estimatedDays": 2.0,
                "priorityRank": 1,
                "urgencyScore": 1.0,
                "warnings": [],
            },
            {
                "readinessId": "RD-BN-2",
                "jiraKey": "BN-2",
                "title": "In progress ticket",
                "estimatedDays": 3.0,
                "priorityRank": 2,
                "urgencyScore": 0.8,
                "warnings": [],
            },
        ],
    }
    persist_selected_sprint(
        project_key=project_key,
        payload=payload,
        memory_patch={
            "sprintNumber": 3,
            "sprintStartDate": "2026-06-03",
            "sprintEndDate": "2026-06-16",
        },
    )

    now = utc_now_iso()
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO work_orders (
                id, jira_key, readiness_id, title, description, priority, status,
                current_stage, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("WO-1", "BN-1", "RD-BN-1", "Done ticket", "", "High", "completed", "done", 0.9, now, now),
                ("WO-2", "BN-2", "RD-BN-2", "In progress ticket", "", "High", "running", "development", 0.8, now, now),
            ],
        )

    snapshot = build_sprint_report_snapshot(project_key=project_key)
    assert snapshot is not None
    assert snapshot["doneTicketKeys"] == ["BN-1"]
    assert snapshot["carryOverTicketKeys"] == ["BN-2"]


def test_publish_sprint_report_creates_invoice_and_includes_url(_isolate_hermes_home):
    from delivery_runtime.readiness.project_settings import persist_project_billing_settings

    project_key = "BN"
    save_delivery_project_config(duration_days=14, capacity_days=15, project_key=project_key)
    persist_project_billing_settings(
        project_key=project_key,
        stripe_customer_id="cus_123",
        daily_rate_cents=80000,
        currency="eur",
        invoice_mode="draft",
        approval_required=False,
        max_invoice_cents=500000,
    )
    _seed_sprint_state(project_key=project_key, sprint_number=2, end_date="2026-06-16")

    now = utc_now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO work_orders (
                id, jira_key, readiness_id, title, description, priority, status,
                current_stage, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("WO-1", "BN-1", "RD-BN-1", "First ticket", "", "High", "completed", "done", 0.9, now, now),
        )

    def fake_billing_agent(snapshot, key):
        assert key == project_key
        return {
            "customerId": "cus_123",
            "currency": "eur",
            "lineItems": [
                {
                    "description": "Delivered BN-1",
                    "ticketKeys": ["BN-1"],
                    "quantityDays": 2.0,
                    "unitAmountCents": 80000,
                }
            ],
            "memo": "Sprint 2 delivery invoice",
            "warnings": [],
        }

    def fake_stripe_invoice(validated, *, invoice_mode):
        assert invoice_mode == "draft"
        assert validated["totalCents"] == 160000
        return {
            "invoiceId": "in_123",
            "invoiceStatus": "draft",
            "invoiceTotalCents": 160000,
            "invoiceCurrency": "eur",
            "invoiceUrl": "https://invoice.stripe.com/in_123",
            "invoicePdfUrl": "https://invoice.stripe.com/in_123.pdf",
        }

    captured_snapshot: dict = {}

    def fake_compose(snapshot, key):
        captured_snapshot.update(snapshot)
        return "Sprint report with invoice"

    first = publish_sprint_report(
        project_key=project_key,
        reporter=fake_compose,
        sender=lambda message: {"success": True, "platform": "slack"},
        billing_agent=fake_billing_agent,
        invoice_creator=fake_stripe_invoice,
    )

    assert first["status"] == "sent"
    assert first["billingStatus"] == "draft_created"
    assert first["invoiceUrl"] == "https://invoice.stripe.com/in_123"
    assert captured_snapshot["billing"]["invoiceUrl"] == "https://invoice.stripe.com/in_123"

    second = publish_sprint_report(
        project_key=project_key,
        force=True,
        reporter=fake_compose,
        sender=lambda message: {"success": True, "platform": "slack"},
        billing_agent=lambda snapshot, key: (_ for _ in ()).throw(AssertionError("must reuse invoice")),
        invoice_creator=fake_stripe_invoice,
    )

    assert second["billingStatus"] == "already_exists"
    assert second["invoiceUrl"] == "https://invoice.stripe.com/in_123"


def test_publish_sprint_report_skips_invoice_when_config_missing(_isolate_hermes_home):
    project_key = "BN"
    save_delivery_project_config(duration_days=14, capacity_days=15, project_key=project_key)
    _seed_sprint_state(project_key=project_key, sprint_number=2, end_date="2026-06-16")

    captured_snapshot: dict = {}

    def _capture_reporter(snapshot, _key):
        captured_snapshot["snapshot"] = snapshot
        return "Sprint report"

    result = publish_sprint_report(
        project_key=project_key,
        reporter=_capture_reporter,
        sender=lambda message: {"success": True, "platform": "slack"},
    )

    assert result["status"] == "sent"
    assert result["billingStatus"] == "skipped"
    assert captured_snapshot["snapshot"]["billing"]["status"] == "skipped"
