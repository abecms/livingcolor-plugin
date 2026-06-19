"""Tests for deterministic sprint invoice guardrails."""

from __future__ import annotations

import pytest

from delivery_runtime.pm_inbox.sprint_invoice import SprintInvoiceError, validate_invoice_proposal


def _billing_snapshot():
    return {
        "customerId": "cus_123",
        "currency": "eur",
        "dailyRateCents": 80000,
        "maxInvoiceCents": 500000,
        "deliveredTickets": [
            {"jiraKey": "BN-1", "title": "First", "estimatedDays": 2.0},
            {"jiraKey": "BN-2", "title": "Second", "estimatedDays": 1.5},
        ],
    }


def test_validate_invoice_proposal_accepts_grouped_delivered_tickets():
    proposal = {
        "customerId": "cus_123",
        "currency": "eur",
        "lineItems": [
            {
                "description": "Delivered sprint tickets BN-1 and BN-2",
                "ticketKeys": ["BN-1", "BN-2"],
                "quantityDays": 3.5,
                "unitAmountCents": 80000,
            }
        ],
        "memo": "Sprint 12 delivery invoice",
        "warnings": [],
    }

    validated = validate_invoice_proposal(proposal, _billing_snapshot())

    assert validated["totalCents"] == 280000
    assert validated["lineItems"][0]["amountCents"] == 280000


@pytest.mark.parametrize(
    ("proposal_patch", "message"),
    [
        ({"customerId": "cus_other"}, "Customer ID does not match configured customer"),
        ({"currency": "usd"}, "Currency does not match configured currency"),
    ],
)
def test_validate_invoice_proposal_rejects_header_mismatch(proposal_patch, message):
    proposal = {
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
    }
    proposal.update(proposal_patch)

    with pytest.raises(SprintInvoiceError, match=message):
        validate_invoice_proposal(proposal, _billing_snapshot())


def test_validate_invoice_proposal_rejects_unknown_ticket():
    proposal = {
        "customerId": "cus_123",
        "currency": "eur",
        "lineItems": [
            {
                "description": "Delivered BN-9",
                "ticketKeys": ["BN-9"],
                "quantityDays": 1.0,
                "unitAmountCents": 80000,
            }
        ],
    }

    with pytest.raises(SprintInvoiceError, match="Unknown delivered ticket BN-9"):
        validate_invoice_proposal(proposal, _billing_snapshot())


def test_validate_invoice_proposal_rejects_duplicate_ticket():
    proposal = {
        "customerId": "cus_123",
        "currency": "eur",
        "lineItems": [
            {"description": "A", "ticketKeys": ["BN-1"], "quantityDays": 2.0, "unitAmountCents": 80000},
            {"description": "B", "ticketKeys": ["BN-1"], "quantityDays": 2.0, "unitAmountCents": 80000},
        ],
    }

    with pytest.raises(SprintInvoiceError, match="Ticket BN-1 is billed more than once"):
        validate_invoice_proposal(proposal, _billing_snapshot())


def test_validate_invoice_proposal_rejects_arbitrary_amount():
    proposal = {
        "customerId": "cus_123",
        "currency": "eur",
        "lineItems": [
            {
                "description": "Delivered BN-1",
                "ticketKeys": ["BN-1"],
                "quantityDays": 2.0,
                "unitAmountCents": 90000,
            }
        ],
    }

    with pytest.raises(SprintInvoiceError, match="Unit amount does not match configured daily rate"):
        validate_invoice_proposal(proposal, _billing_snapshot())


def test_validate_invoice_proposal_rejects_total_above_cap():
    snapshot = _billing_snapshot()
    snapshot["deliveredTickets"] = [
        {"jiraKey": "BN-1", "title": "First", "estimatedDays": 2.0},
    ]
    snapshot["maxInvoiceCents"] = 100000
    proposal = {
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
    }

    with pytest.raises(SprintInvoiceError, match="Invoice total exceeds billingMaxInvoiceCents"):
        validate_invoice_proposal(proposal, snapshot)
