"""Tests for sprint invoice snapshot construction."""

from __future__ import annotations

from delivery_runtime.pm_inbox.sprint_invoice import build_sprint_billing_snapshot


def test_billing_snapshot_includes_only_delivered_ticket_details():
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
            {"jiraKey": "BN-1", "title": "Delivered one", "estimatedDays": 2.0},
            {"jiraKey": "BN-2", "title": "Carry over", "estimatedDays": 3.0},
        ],
        "deliveredTicketKeys": ["BN-1"],
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
    assert billing["deliveredTickets"] == [
        {"jiraKey": "BN-1", "title": "Delivered one", "estimatedDays": 2.0}
    ]
    assert billing["warnings"] == []


def test_billing_snapshot_marks_missing_estimates():
    report_snapshot = {
        "projectKey": "BN",
        "projectName": "Bibliotheque Numerique",
        "sprintNumber": 12,
        "sprint": {"name": "Sprint 12", "endDate": "2026-06-30"},
        "ticketsPlanned": [
            {"jiraKey": "BN-1", "title": "Delivered one", "estimatedDays": None},
        ],
        "deliveredTicketKeys": ["BN-1"],
    }

    billing = build_sprint_billing_snapshot(
        report_snapshot,
        customer_id="cus_123",
        daily_rate_cents=80000,
        currency="eur",
        max_invoice_cents=None,
    )

    assert billing["deliveredTickets"][0]["estimatedDays"] is None
    assert billing["warnings"] == ["Missing estimate for delivered ticket BN-1"]
