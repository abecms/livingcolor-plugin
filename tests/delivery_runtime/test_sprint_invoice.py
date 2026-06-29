"""Tests for sprint invoice snapshot construction."""

from __future__ import annotations

from delivery_runtime.pm_inbox.sprint_invoice import build_sprint_billing_snapshot


def test_billing_snapshot_includes_only_done_ticket_details():
    report_snapshot = {
        "projectKey": "BN",
        "projectName": "Bibliotheque Numerique",
        "sprintNumber": 12,
        "sprint": {
            "name": "Sprint 12",
            "startDate": "2026-06-17",
            "endDate": "2026-06-30",
        },
        "ticketsPlanned": [
            {
                "jiraKey": "BN-1",
                "title": "Done one",
                "estimatedDays": 2.0,
                "workOrderStatus": "completed",
            },
            {
                "jiraKey": "BN-2",
                "title": "Carry over",
                "estimatedDays": 3.0,
                "workOrderStatus": "running",
            },
        ],
        "doneTicketKeys": ["BN-1", "BN-2"],
    }

    billing = build_sprint_billing_snapshot(
        report_snapshot,
        customer_id="cus_123",
        daily_rate_cents=80000,
        currency="eur",
        max_invoice_cents=300000,
    )

    assert billing["projectKey"] == "BN"
    assert billing["dedupKey"] == "12:2026-06-30"
    assert billing["customerId"] == "cus_123"
    assert billing["dailyRateCents"] == 80000
    assert billing["currency"] == "eur"
    assert billing["maxInvoiceCents"] == 300000
    assert billing["doneTickets"] == [
        {"jiraKey": "BN-1", "title": "Done one", "estimatedDays": 2.0}
    ]
    assert billing["warnings"] == []


def test_billing_snapshot_marks_missing_estimates_without_blocking_other_done_tickets():
    report_snapshot = {
        "projectKey": "BN",
        "projectName": "Bibliotheque Numerique",
        "sprintNumber": 12,
        "sprint": {"name": "Sprint 12", "endDate": "2026-06-30"},
        "ticketsPlanned": [
            {
                "jiraKey": "BN-1",
                "title": "Done without estimate",
                "estimatedDays": None,
                "workOrderStatus": "completed",
            },
            {
                "jiraKey": "BN-2",
                "title": "Done with estimate",
                "estimatedDays": 1.5,
                "workOrderStatus": "completed",
            },
        ],
        "doneTicketKeys": ["BN-1", "BN-2"],
    }

    billing = build_sprint_billing_snapshot(
        report_snapshot,
        customer_id="cus_123",
        daily_rate_cents=80000,
        currency="eur",
        max_invoice_cents=None,
    )

    assert billing["doneTickets"] == [
        {"jiraKey": "BN-1", "title": "Done without estimate", "estimatedDays": None},
        {"jiraKey": "BN-2", "title": "Done with estimate", "estimatedDays": 1.5},
    ]
    assert billing["warnings"] == ["Missing estimate for done ticket BN-1"]


def test_billing_snapshot_ignores_done_keys_without_completed_work_order_status():
    report_snapshot = {
        "projectKey": "BN",
        "sprintNumber": 12,
        "sprint": {"endDate": "2026-06-30"},
        "ticketsPlanned": [
            {
                "jiraKey": "BN-1",
                "title": "Still in dev",
                "estimatedDays": 2.0,
                "workOrderStatus": "running",
            }
        ],
        "doneTicketKeys": ["BN-1"],
    }

    billing = build_sprint_billing_snapshot(
        report_snapshot,
        customer_id="cus_123",
        daily_rate_cents=80000,
        currency="eur",
        max_invoice_cents=None,
    )

    assert billing["doneTickets"] == []
    assert billing["warnings"] == []
