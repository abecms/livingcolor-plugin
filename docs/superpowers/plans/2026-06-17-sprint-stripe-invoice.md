# Sprint Stripe Invoice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LLM-built, guardrail-validated Stripe invoice generation to the existing end-of-sprint report flow.

**Architecture:** Extend the existing `publish_sprint_report` path. The delivery runtime builds a deterministic billing snapshot and validates invoice proposals; `lc_server` owns the Hermes billing agent and Stripe API adapter. Billing failures enrich the report with warnings but do not block report publication.

**Tech Stack:** Python 3.13, FastAPI, SQLite sprint memory, pytest, Hermes `AIAgent`, Stripe Billing API via injectable client wrapper.

**Spec:** `docs/superpowers/specs/2026-06-17-sprint-stripe-invoice-design.md`

---

## File Map

| Task | Create | Modify |
| --- | --- | --- |
| 1 | `tests/delivery_runtime/test_billing_config.py` | `delivery_runtime/automation/config.py`, `delivery_runtime/readiness/project_settings.py` |
| 2 | `delivery_runtime/pm_inbox/sprint_invoice.py`, `tests/delivery_runtime/test_sprint_invoice.py` | none |
| 3 | `tests/delivery_runtime/test_sprint_invoice_validation.py` | `delivery_runtime/pm_inbox/sprint_invoice.py` |
| 4 | `lc_server/agent_bridge/hermes_sprint_billing.py`, `tests/lc_server/test_hermes_sprint_billing_agent.py` | none |
| 5 | `lc_server/integrations/stripe_billing.py`, `tests/lc_server/test_stripe_billing.py` | none |
| 6 | none | `delivery_runtime/pm_inbox/sprint_report.py`, `tests/delivery_runtime/test_sprint_report.py` |
| 7 | none | `lc_server/agent_bridge/hermes_sprint_reporter.py`, `tests/lc_server/test_external_skills_prompt_injection.py` |
| 8 | none | `delivery_runtime/api/schemas.py`, `tests/delivery_runtime/test_automation_api.py`, `README.md` |

## Task 1: Billing Configuration

**Files:**
- Create: `tests/delivery_runtime/test_billing_config.py`
- Modify: `delivery_runtime/automation/config.py`
- Modify: `delivery_runtime/readiness/project_settings.py`

- [ ] **Step 1: Write failing tests for billing config defaults and project mapping**

Create `tests/delivery_runtime/test_billing_config.py`:

```python
"""Tests for project-level sprint billing configuration."""

from __future__ import annotations

from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.readiness.project_settings import (
    BillingSettings,
    load_project_billing_settings,
    persist_project_billing_settings,
)


def test_billing_config_defaults_are_safe(_isolate_hermes_home):
    config = load_delivery_automation_config(project_key="BN")

    assert config.billing.stripe_customer_id is None
    assert config.billing.daily_rate_cents is None
    assert config.billing.currency == "eur"
    assert config.billing.invoice_mode == "draft"
    assert config.billing.approval_required is False
    assert config.billing.max_invoice_cents is None


def test_project_billing_settings_round_trip(_isolate_hermes_home):
    saved = persist_project_billing_settings(
        project_key="BN",
        stripe_customer_id="cus_123",
        daily_rate_cents=80000,
        currency="EUR",
        invoice_mode="finalize",
        approval_required=True,
        max_invoice_cents=500000,
    )

    assert saved == BillingSettings(
        stripe_customer_id="cus_123",
        daily_rate_cents=80000,
        currency="eur",
        invoice_mode="finalize",
        approval_required=True,
        max_invoice_cents=500000,
    )

    loaded = load_project_billing_settings("BN")
    assert loaded == saved

    config = load_delivery_automation_config(project_key="BN")
    assert config.billing == saved
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/delivery_runtime/test_billing_config.py -v
```

Expected: FAIL with import errors for `BillingSettings`, `load_project_billing_settings`, and missing `config.billing`.

- [ ] **Step 3: Add billing settings helpers**

In `delivery_runtime/readiness/project_settings.py`, add the dataclass after `ProjectDeliverySettings`:

```python
@dataclass(frozen=True)
class BillingSettings:
    stripe_customer_id: str | None = None
    daily_rate_cents: int | None = None
    currency: str = "eur"
    invoice_mode: str = "draft"
    approval_required: bool = False
    max_invoice_cents: int | None = None
```

Add these helpers after `load_project_delivery_settings`:

```python
def _normalize_optional_positive_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalize_billing_currency(value: Any) -> str:
    text = str(value or "eur").strip().lower()
    return text if len(text) == 3 and text.isalpha() else "eur"


def _normalize_invoice_mode(value: Any) -> str:
    text = str(value or "draft").strip().lower()
    return text if text in {"draft", "finalize"} else "draft"


def load_project_billing_settings(project_key: str) -> BillingSettings:
    key = _normalize_project_key(project_key)
    if not key:
        return BillingSettings()

    entry = _mapping_entry(key)
    billing = entry.get("billing")
    billing_map = billing if isinstance(billing, dict) else {}
    stripe_customer_id = str(
        billing_map.get("stripe_customer_id")
        or billing_map.get("stripeCustomerId")
        or ""
    ).strip()

    return BillingSettings(
        stripe_customer_id=stripe_customer_id or None,
        daily_rate_cents=_normalize_optional_positive_int(
            billing_map.get("daily_rate_cents") or billing_map.get("billingDailyRateCents")
        ),
        currency=_normalize_billing_currency(
            billing_map.get("currency") or billing_map.get("billingCurrency")
        ),
        invoice_mode=_normalize_invoice_mode(
            billing_map.get("invoice_mode") or billing_map.get("billingInvoiceMode")
        ),
        approval_required=bool(
            billing_map.get("approval_required") or billing_map.get("billingApprovalRequired") or False
        ),
        max_invoice_cents=_normalize_optional_positive_int(
            billing_map.get("max_invoice_cents") or billing_map.get("billingMaxInvoiceCents")
        ),
    )


def persist_project_billing_settings(
    *,
    project_key: str,
    stripe_customer_id: str | None,
    daily_rate_cents: int | None,
    currency: str = "eur",
    invoice_mode: str = "draft",
    approval_required: bool = False,
    max_invoice_cents: int | None = None,
) -> BillingSettings:
    key = _normalize_project_key(project_key)
    if not key:
        raise ValueError("project_key is required")

    settings = BillingSettings(
        stripe_customer_id=(stripe_customer_id or "").strip() or None,
        daily_rate_cents=_normalize_optional_positive_int(daily_rate_cents),
        currency=_normalize_billing_currency(currency),
        invoice_mode=_normalize_invoice_mode(invoice_mode),
        approval_required=bool(approval_required),
        max_invoice_cents=_normalize_optional_positive_int(max_invoice_cents),
    )

    def _update(entry: dict[str, Any]) -> None:
        entry["billing"] = {
            "stripe_customer_id": settings.stripe_customer_id,
            "daily_rate_cents": settings.daily_rate_cents,
            "currency": settings.currency,
            "invoice_mode": settings.invoice_mode,
            "approval_required": settings.approval_required,
            "max_invoice_cents": settings.max_invoice_cents,
        }

    _upsert_mapping_entry(key, _update)
    return settings
```

- [ ] **Step 4: Wire billing into automation config**

In `delivery_runtime/automation/config.py`, import no new modules at top level. Add a field to `DeliveryAutomationConfig`:

```python
    billing: "BillingSettings | None" = None
```

Inside `load_delivery_automation_config`, update the project settings import block:

```python
    from delivery_runtime.readiness.project_settings import (
        load_project_billing_settings,
        load_project_delivery_settings,
        mapping_has_delivery_settings,
    )
```

Before returning `DeliveryAutomationConfig`, add:

```python
    billing = load_project_billing_settings(project_key_resolved)
```

Add the field to the return object:

```python
        billing=billing,
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/delivery_runtime/test_billing_config.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add delivery_runtime/automation/config.py delivery_runtime/readiness/project_settings.py tests/delivery_runtime/test_billing_config.py
git commit -m "feat: add sprint billing project config"
```

## Task 2: Sprint Billing Snapshot

**Files:**
- Create: `delivery_runtime/pm_inbox/sprint_invoice.py`
- Create: `tests/delivery_runtime/test_sprint_invoice.py`

- [ ] **Step 1: Write failing tests for snapshot extraction**

Create `tests/delivery_runtime/test_sprint_invoice.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/delivery_runtime/test_sprint_invoice.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'delivery_runtime.pm_inbox.sprint_invoice'`.

- [ ] **Step 3: Create sprint invoice snapshot module**

Create `delivery_runtime/pm_inbox/sprint_invoice.py`:

```python
"""Sprint invoice proposal and validation helpers."""

from __future__ import annotations

from typing import Any

from delivery_runtime.pm_inbox.sprint_report import sprint_report_dedup_key


class SprintInvoiceError(ValueError):
    """Raised when a sprint invoice proposal cannot be accepted."""


def _ticket_key(value: Any) -> str:
    return str(value or "").strip().upper()


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_sprint_billing_snapshot(
    report_snapshot: dict[str, Any],
    *,
    customer_id: str,
    daily_rate_cents: int,
    currency: str,
    max_invoice_cents: int | None,
) -> dict[str, Any]:
    sprint = report_snapshot.get("sprint") or {}
    sprint_number = int(report_snapshot.get("sprintNumber") or sprint.get("number") or 0)
    sprint_end_date = str(sprint.get("endDate") or "")
    dedup_key = sprint_report_dedup_key(
        sprint_number=sprint_number,
        sprint_end_date=sprint_end_date,
    )

    delivered_keys = {
        _ticket_key(key)
        for key in report_snapshot.get("deliveredTicketKeys") or []
        if _ticket_key(key)
    }

    delivered_tickets: list[dict[str, Any]] = []
    warnings: list[str] = []
    for item in report_snapshot.get("ticketsPlanned") or []:
        if not isinstance(item, dict):
            continue
        key = _ticket_key(item.get("jiraKey"))
        if key not in delivered_keys:
            continue
        estimated_days = _optional_float(item.get("estimatedDays"))
        if estimated_days is None:
            warnings.append(f"Missing estimate for delivered ticket {key}")
        delivered_tickets.append(
            {
                "jiraKey": key,
                "title": str(item.get("title") or "").strip(),
                "estimatedDays": estimated_days,
            }
        )

    return {
        "projectKey": str(report_snapshot.get("projectKey") or "").strip().upper(),
        "projectName": str(report_snapshot.get("projectName") or "").strip(),
        "sprintNumber": sprint_number,
        "sprint": {
            "name": sprint.get("name"),
            "startDate": sprint.get("startDate"),
            "endDate": sprint_end_date,
        },
        "dedupKey": dedup_key,
        "customerId": customer_id,
        "dailyRateCents": int(daily_rate_cents),
        "currency": str(currency or "eur").strip().lower(),
        "maxInvoiceCents": max_invoice_cents,
        "deliveredTickets": delivered_tickets,
        "warnings": warnings,
    }
```

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/delivery_runtime/test_sprint_invoice.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add delivery_runtime/pm_inbox/sprint_invoice.py tests/delivery_runtime/test_sprint_invoice.py
git commit -m "feat: build sprint billing snapshot"
```

## Task 3: Invoice Proposal Validation

**Files:**
- Modify: `delivery_runtime/pm_inbox/sprint_invoice.py`
- Create: `tests/delivery_runtime/test_sprint_invoice_validation.py`

- [ ] **Step 1: Write failing validation tests**

Create `tests/delivery_runtime/test_sprint_invoice_validation.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/delivery_runtime/test_sprint_invoice_validation.py -v
```

Expected: FAIL because `validate_invoice_proposal` does not exist.

- [ ] **Step 3: Implement validation**

Append to `delivery_runtime/pm_inbox/sprint_invoice.py`:

```python
def _as_ticket_keys(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_ticket_key(item) for item in value if _ticket_key(item)]


def _line_quantity(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise SprintInvoiceError("Line item quantityDays must be numeric")
    if parsed <= 0:
        raise SprintInvoiceError("Line item quantityDays must be positive")
    return parsed


def _line_unit_amount(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise SprintInvoiceError("Line item unitAmountCents must be numeric")
    if parsed <= 0:
        raise SprintInvoiceError("Line item unitAmountCents must be positive")
    return parsed


def validate_invoice_proposal(proposal: dict[str, Any], billing_snapshot: dict[str, Any]) -> dict[str, Any]:
    customer_id = str(billing_snapshot.get("customerId") or "").strip()
    currency = str(billing_snapshot.get("currency") or "eur").strip().lower()
    daily_rate = int(billing_snapshot.get("dailyRateCents") or 0)
    max_invoice = billing_snapshot.get("maxInvoiceCents")

    if str(proposal.get("customerId") or "").strip() != customer_id:
        raise SprintInvoiceError("Customer ID does not match configured customer")
    if str(proposal.get("currency") or "").strip().lower() != currency:
        raise SprintInvoiceError("Currency does not match configured currency")

    delivered = {
        _ticket_key(item.get("jiraKey")): _optional_float(item.get("estimatedDays"))
        for item in billing_snapshot.get("deliveredTickets") or []
        if isinstance(item, dict) and _ticket_key(item.get("jiraKey"))
    }
    if not delivered:
        raise SprintInvoiceError("No delivered tickets are billable")
    if any(value is None for value in delivered.values()):
        raise SprintInvoiceError("Delivered tickets with missing estimates cannot be invoiced")

    line_items = proposal.get("lineItems")
    if not isinstance(line_items, list) or not line_items:
        raise SprintInvoiceError("Invoice proposal must include at least one line item")

    seen: set[str] = set()
    validated_lines: list[dict[str, Any]] = []
    total_cents = 0
    for line in line_items:
        if not isinstance(line, dict):
            raise SprintInvoiceError("Invoice line item must be an object")
        keys = _as_ticket_keys(line.get("ticketKeys"))
        if not keys:
            raise SprintInvoiceError("Invoice line item must reference delivered tickets")
        for key in keys:
            if key not in delivered:
                raise SprintInvoiceError(f"Unknown delivered ticket {key}")
            if key in seen:
                raise SprintInvoiceError(f"Ticket {key} is billed more than once")
            seen.add(key)

        expected_quantity = sum(float(delivered[key] or 0) for key in keys)
        quantity = _line_quantity(line.get("quantityDays"))
        if abs(quantity - expected_quantity) > 0.001:
            raise SprintInvoiceError("Line quantityDays does not match delivered ticket estimates")

        unit_amount = _line_unit_amount(line.get("unitAmountCents"))
        if unit_amount != daily_rate:
            raise SprintInvoiceError("Unit amount does not match configured daily rate")

        amount_cents = int(round(quantity * unit_amount))
        total_cents += amount_cents
        validated_lines.append(
            {
                "description": str(line.get("description") or "").strip() or ", ".join(keys),
                "ticketKeys": keys,
                "quantityDays": quantity,
                "unitAmountCents": unit_amount,
                "amountCents": amount_cents,
            }
        )

    missing = sorted(set(delivered) - seen)
    if missing:
        raise SprintInvoiceError(f"Delivered ticket {missing[0]} is not included in invoice proposal")

    if max_invoice is not None and total_cents > int(max_invoice):
        raise SprintInvoiceError("Invoice total exceeds billingMaxInvoiceCents")

    return {
        "customerId": customer_id,
        "currency": currency,
        "lineItems": validated_lines,
        "memo": str(proposal.get("memo") or "").strip(),
        "warnings": list(proposal.get("warnings") or []),
        "totalCents": total_cents,
    }
```

- [ ] **Step 4: Run validation tests**

Run:

```bash
pytest tests/delivery_runtime/test_sprint_invoice_validation.py tests/delivery_runtime/test_sprint_invoice.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add delivery_runtime/pm_inbox/sprint_invoice.py tests/delivery_runtime/test_sprint_invoice_validation.py
git commit -m "feat: validate sprint invoice proposals"
```

## Task 4: Hermes Sprint Billing Agent

**Files:**
- Create: `lc_server/agent_bridge/hermes_sprint_billing.py`
- Create: `tests/lc_server/test_hermes_sprint_billing_agent.py`

- [ ] **Step 1: Write failing tests for LLM proposal extraction**

Create `tests/lc_server/test_hermes_sprint_billing_agent.py`:

````python
"""Tests for the Hermes sprint billing agent."""

from __future__ import annotations

from dataclasses import dataclass

from lc_server.agent_bridge.hermes_sprint_billing import HermesSprintBillingAgent


def test_sprint_billing_agent_returns_json_proposal(monkeypatch):
    prompts: list[str] = []

    @dataclass
    class CapturingAgent:
        def run_conversation(self, prompt: str, *, task_id: str):
            prompts.append(prompt)
            return {
                "final_response": """
```json
{
  "customerId": "cus_123",
  "currency": "eur",
  "lineItems": [
    {
      "description": "Delivered BN-1",
      "ticketKeys": ["BN-1"],
      "quantityDays": 2.0,
      "unitAmountCents": 80000
    }
  ],
  "memo": "Sprint 12 delivery invoice",
  "warnings": []
}
```
"""
            }

    agent = HermesSprintBillingAgent(agent_factory=lambda **kwargs: CapturingAgent())
    proposal = agent.propose(
        {
            "projectKey": "BN",
            "sprintNumber": 12,
            "dedupKey": "12:2026-06-30",
            "customerId": "cus_123",
            "currency": "eur",
            "dailyRateCents": 80000,
            "deliveredTickets": [{"jiraKey": "BN-1", "title": "Delivered", "estimatedDays": 2.0}],
        },
        project_key="BN",
    )

    assert proposal["customerId"] == "cus_123"
    assert proposal["lineItems"][0]["ticketKeys"] == ["BN-1"]
    assert "Output ONLY valid JSON" in prompts[0]
    assert "cus_123" in prompts[0]
````

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/lc_server/test_hermes_sprint_billing_agent.py -v
```

Expected: FAIL because `lc_server.agent_bridge.hermes_sprint_billing` does not exist.

- [ ] **Step 3: Implement billing agent**

Create `lc_server/agent_bridge/hermes_sprint_billing.py`:

```python
"""Hermes-backed sprint billing proposal agent."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

SPRINT_BILLING_SYSTEM_PROMPT = """You are the LivingColor Sprint Billing Agent.

Build a Stripe invoice proposal from the provided sprint billing snapshot.

Rules:
- Output ONLY valid JSON.
- Use only delivered tickets from the snapshot.
- Do not invent ticket keys, quantities, currency, customer IDs, or prices.
- You may group delivered tickets into one line when the description remains clear.
- Every delivered ticket must appear exactly once.
- Keep descriptions concise and client-ready.
"""

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class SprintBillingAgentError(RuntimeError):
    """Sprint billing agent could not produce a valid proposal."""


class HermesSprintBillingAgent:
    def __init__(self, *, agent_factory: Callable[..., Any] | None = None) -> None:
        self._agent_factory = agent_factory or _default_sprint_billing_agent_factory

    def propose(self, billing_snapshot: dict[str, Any], *, project_key: str) -> dict[str, Any]:
        key = project_key.strip().upper()
        task_id = f"delivery-sprint-billing-{key}-{billing_snapshot.get('dedupKey') or 'unknown'}"
        prompt = (
            f"{SPRINT_BILLING_SYSTEM_PROMPT}\n\n"
            "Sprint billing snapshot:\n"
            f"{json.dumps(billing_snapshot, indent=2, ensure_ascii=False)}"
        )
        agent = self._agent_factory(task_id=task_id, project_key=key)
        result = agent.run_conversation(prompt, task_id=task_id)
        raw = str(result.get("final_response") or "").strip()
        cleaned = _JSON_FENCE_RE.sub("", raw).strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise SprintBillingAgentError("Sprint billing agent returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise SprintBillingAgentError("Sprint billing agent proposal must be a JSON object")
        return parsed


def _default_sprint_billing_agent_factory(*, task_id: str, project_key: str) -> Any:
    from hermes_cli.config import load_config
    from hermes_cli.fallback_config import get_fallback_chain
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from lc_server.env_loader import prepare_delivery_agent_environment
    from run_agent import AIAgent

    prepare_delivery_agent_environment()
    os.environ.setdefault("HERMES_YOLO_MODE", "1")
    os.environ.setdefault("HERMES_ACCEPT_HOOKS", "1")

    cfg = load_config()
    model_cfg = cfg.get("model") or {}
    if isinstance(model_cfg, str):
        effective_model = model_cfg
        cfg_provider = ""
    else:
        effective_model = str(model_cfg.get("default") or model_cfg.get("model") or "")
        cfg_provider = str(model_cfg.get("provider") or "").strip()

    effective_model = os.getenv("HERMES_INFERENCE_MODEL", "").strip() or effective_model
    effective_provider = os.getenv("HERMES_INFERENCE_PROVIDER", "").strip() or cfg_provider or None
    runtime = resolve_runtime_provider(requested=effective_provider, target_model=effective_model or None)

    return AIAgent(
        api_key=runtime.get("api_key"),
        base_url=runtime.get("base_url"),
        provider=runtime.get("provider"),
        api_mode=runtime.get("api_mode"),
        model=effective_model,
        enabled_toolsets=[],
        max_iterations=6,
        quiet_mode=True,
        platform="livingcolor-sprint-billing",
        session_id=task_id,
        ephemeral_system_prompt=SPRINT_BILLING_SYSTEM_PROMPT,
        skip_context_files=True,
        skip_memory=True,
        fallback_model=get_fallback_chain(cfg) or None,
        credential_pool=runtime.get("credential_pool"),
    )
```

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/lc_server/test_hermes_sprint_billing_agent.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lc_server/agent_bridge/hermes_sprint_billing.py tests/lc_server/test_hermes_sprint_billing_agent.py
git commit -m "feat: add Hermes sprint billing agent"
```

## Task 5: Stripe Billing Adapter

**Files:**
- Create: `lc_server/integrations/stripe_billing.py`
- Create: `tests/lc_server/test_stripe_billing.py`

- [ ] **Step 1: Write failing adapter tests with fake Stripe client**

Create `tests/lc_server/test_stripe_billing.py`:

```python
"""Tests for Stripe invoice creation adapter."""

from __future__ import annotations

from lc_server.integrations.stripe_billing import create_sprint_invoice


class FakeStripeClient:
    def __init__(self):
        self.invoice_items: list[dict] = []
        self.created_invoices: list[dict] = []
        self.finalized: list[str] = []

    class InvoiceItem:
        @staticmethod
        def create(**kwargs):
            raise AssertionError("InvoiceItem.create must be patched")

    class Invoice:
        @staticmethod
        def create(**kwargs):
            raise AssertionError("Invoice.create must be patched")

        @staticmethod
        def finalize_invoice(invoice_id):
            raise AssertionError("Invoice.finalize_invoice must be patched")


def test_create_sprint_invoice_creates_items_and_draft(monkeypatch):
    fake = FakeStripeClient()

    def create_item(**kwargs):
        fake.invoice_items.append(kwargs)
        return {"id": f"ii_{len(fake.invoice_items)}"}

    def create_invoice(**kwargs):
        fake.created_invoices.append(kwargs)
        return {
            "id": "in_123",
            "status": "draft",
            "total": 160000,
            "currency": "eur",
            "hosted_invoice_url": "https://invoice.stripe.com/in_123",
            "invoice_pdf": "https://invoice.stripe.com/in_123.pdf",
        }

    fake.InvoiceItem.create = staticmethod(create_item)
    fake.Invoice.create = staticmethod(create_invoice)

    result = create_sprint_invoice(
        {
            "customerId": "cus_123",
            "currency": "eur",
            "lineItems": [
                {
                    "description": "Delivered BN-1",
                    "quantityDays": 2.0,
                    "unitAmountCents": 80000,
                    "amountCents": 160000,
                    "ticketKeys": ["BN-1"],
                }
            ],
            "memo": "Sprint 12 delivery invoice",
            "totalCents": 160000,
        },
        invoice_mode="draft",
        stripe_client=fake,
    )

    assert fake.invoice_items == [
        {
            "customer": "cus_123",
            "currency": "eur",
            "amount": 160000,
            "description": "Delivered BN-1",
            "metadata": {"ticketKeys": "BN-1"},
        }
    ]
    assert fake.created_invoices[0]["customer"] == "cus_123"
    assert fake.created_invoices[0]["description"] == "Sprint 12 delivery invoice"
    assert result["invoiceId"] == "in_123"
    assert result["invoiceStatus"] == "draft"
    assert result["invoiceUrl"] == "https://invoice.stripe.com/in_123"


def test_create_sprint_invoice_finalizes_when_requested(monkeypatch):
    fake = FakeStripeClient()
    fake.InvoiceItem.create = staticmethod(lambda **kwargs: {"id": "ii_123"})
    fake.Invoice.create = staticmethod(lambda **kwargs: {"id": "in_123", "status": "draft", "total": 0, "currency": "eur"})
    fake.Invoice.finalize_invoice = staticmethod(
        lambda invoice_id: {
            "id": invoice_id,
            "status": "open",
            "total": 160000,
            "currency": "eur",
            "hosted_invoice_url": "https://invoice.stripe.com/in_123",
            "invoice_pdf": "https://invoice.stripe.com/in_123.pdf",
        }
    )

    result = create_sprint_invoice(
        {
            "customerId": "cus_123",
            "currency": "eur",
            "lineItems": [
                {"description": "Delivered BN-1", "quantityDays": 2.0, "unitAmountCents": 80000, "amountCents": 160000, "ticketKeys": ["BN-1"]}
            ],
            "memo": "Sprint 12 delivery invoice",
            "totalCents": 160000,
        },
        invoice_mode="finalize",
        stripe_client=fake,
    )

    assert result["invoiceStatus"] == "open"
    assert result["invoiceUrl"] == "https://invoice.stripe.com/in_123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/lc_server/test_stripe_billing.py -v
```

Expected: FAIL because `lc_server.integrations.stripe_billing` does not exist.

- [ ] **Step 3: Implement Stripe adapter with injectable client**

Create `lc_server/integrations/stripe_billing.py`:

```python
"""Stripe Billing adapter for sprint invoices."""

from __future__ import annotations

from typing import Any


class StripeBillingError(RuntimeError):
    """Raised when Stripe invoice creation fails."""


def _default_stripe_client() -> Any:
    try:
        import stripe
    except ImportError as exc:
        raise StripeBillingError("Stripe SDK is not installed in this environment") from exc
    return stripe


def _invoice_payload(invoice: Any) -> dict[str, Any]:
    getter = invoice.get if isinstance(invoice, dict) else lambda key, default=None: getattr(invoice, key, default)
    return {
        "invoiceId": getter("id"),
        "invoiceStatus": getter("status"),
        "invoiceTotalCents": getter("total"),
        "invoiceCurrency": getter("currency"),
        "invoiceUrl": getter("hosted_invoice_url"),
        "invoicePdfUrl": getter("invoice_pdf"),
    }


def create_sprint_invoice(
    validated_invoice: dict[str, Any],
    *,
    invoice_mode: str,
    stripe_client: Any | None = None,
) -> dict[str, Any]:
    client = stripe_client or _default_stripe_client()
    customer_id = str(validated_invoice["customerId"])
    currency = str(validated_invoice["currency"])

    for line in validated_invoice.get("lineItems") or []:
        client.InvoiceItem.create(
            customer=customer_id,
            currency=currency,
            amount=int(line["amountCents"]),
            description=str(line["description"]),
            metadata={"ticketKeys": ",".join(line.get("ticketKeys") or [])},
        )

    invoice = client.Invoice.create(
        customer=customer_id,
        description=str(validated_invoice.get("memo") or ""),
        auto_advance=False,
        metadata={"source": "livingcolor_sprint_report"},
    )

    if invoice_mode == "finalize":
        invoice_id = invoice["id"] if isinstance(invoice, dict) else invoice.id
        invoice = client.Invoice.finalize_invoice(invoice_id)

    return _invoice_payload(invoice)
```

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/lc_server/test_stripe_billing.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lc_server/integrations/stripe_billing.py tests/lc_server/test_stripe_billing.py
git commit -m "feat: add Stripe sprint invoice adapter"
```

## Task 6: Integrate Billing Into Sprint Report

**Files:**
- Modify: `delivery_runtime/pm_inbox/sprint_report.py`
- Modify: `tests/delivery_runtime/test_sprint_report.py`

- [ ] **Step 1: Add failing tests for invoice creation and deduplication**

Append to `tests/delivery_runtime/test_sprint_report.py`:

```python
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
    result = publish_sprint_report(
        project_key=project_key,
        reporter=lambda snapshot, key: captured_snapshot.setdefault("snapshot", snapshot) or "Sprint report",
        sender=lambda message: {"success": True, "platform": "slack"},
    )

    assert result["status"] == "sent"
    assert result["billingStatus"] == "skipped"
    assert captured_snapshot["snapshot"]["billing"]["status"] == "skipped"
```

- [ ] **Step 2: Run targeted tests to verify they fail**

Run:

```bash
pytest tests/delivery_runtime/test_sprint_report.py -v
```

Expected: FAIL because `publish_sprint_report` does not accept `billing_agent` or `invoice_creator`.

- [ ] **Step 3: Add billing orchestration helpers**

In `delivery_runtime/pm_inbox/sprint_report.py`, update imports:

```python
from delivery_runtime.pm_inbox.sprint_invoice import (
    SprintInvoiceError,
    build_sprint_billing_snapshot,
    validate_invoice_proposal,
)
```

Add type parameters to `publish_sprint_report`:

```python
    billing_agent: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
    invoice_creator: Callable[..., dict[str, Any]] | None = None,
```

Add helper functions before `publish_sprint_report`:

```python
def _existing_invoice_result(memory: dict[str, Any], dedup_key: str) -> dict[str, Any] | None:
    if str(memory.get("lastSprintInvoiceKey") or "") != dedup_key:
        return None
    invoice_url = str(memory.get("lastSprintInvoiceUrl") or "").strip()
    invoice_id = str(memory.get("lastSprintInvoiceId") or "").strip()
    if not invoice_url and not invoice_id:
        return None
    return {
        "status": "already_exists",
        "invoiceId": invoice_id or None,
        "invoiceUrl": invoice_url or None,
        "invoiceStatus": memory.get("lastSprintInvoiceStatus"),
        "invoiceTotalCents": memory.get("lastSprintInvoiceTotalCents"),
        "invoiceCurrency": memory.get("lastSprintInvoiceCurrency"),
    }


def _billing_skip(reason: str) -> dict[str, Any]:
    return {"status": "skipped", "warning": reason}


def _default_billing_agent(snapshot: dict[str, Any], project_key: str) -> dict[str, Any]:
    from lc_server.agent_bridge.hermes_sprint_billing import HermesSprintBillingAgent

    return HermesSprintBillingAgent().propose(snapshot, project_key=project_key)


def _default_invoice_creator(validated_invoice: dict[str, Any], *, invoice_mode: str) -> dict[str, Any]:
    from lc_server.integrations.stripe_billing import create_sprint_invoice

    return create_sprint_invoice(validated_invoice, invoice_mode=invoice_mode)
```

Add this helper:

```python
def _create_or_reuse_sprint_invoice(
    *,
    project_key: str,
    snapshot: dict[str, Any],
    dedup_key: str,
    memory: dict[str, Any],
    actor: str,
    billing_agent: Callable[[dict[str, Any], str], dict[str, Any]] | None,
    invoice_creator: Callable[..., dict[str, Any]] | None,
) -> dict[str, Any]:
    existing = _existing_invoice_result(memory, dedup_key)
    if existing:
        return existing

    config = load_delivery_automation_config(project_key=project_key)
    billing = config.billing
    if not billing or not billing.stripe_customer_id:
        return _billing_skip("Stripe customer is not configured")
    if not billing.daily_rate_cents:
        return _billing_skip("Billing daily rate is not configured")

    billing_snapshot = build_sprint_billing_snapshot(
        snapshot,
        customer_id=billing.stripe_customer_id,
        daily_rate_cents=billing.daily_rate_cents,
        currency=billing.currency,
        max_invoice_cents=billing.max_invoice_cents,
    )
    if billing_snapshot["warnings"]:
        return _billing_skip("; ".join(billing_snapshot["warnings"]))

    propose = billing_agent or _default_billing_agent
    create_invoice = invoice_creator or _default_invoice_creator

    try:
        proposal = propose(billing_snapshot, project_key)
        EventStore().append(
            event_type="SPRINT_INVOICE_PROPOSED",
            actor=actor,
            payload={"projectKey": project_key, "dedupKey": dedup_key},
        )
        validated = validate_invoice_proposal(proposal, billing_snapshot)
        invoice_mode = "draft" if billing.approval_required else billing.invoice_mode
        invoice = create_invoice(validated, invoice_mode=invoice_mode)
    except (SprintInvoiceError, Exception) as exc:
        logger.exception("Sprint invoice generation failed for %s", project_key)
        EventStore().append(
            event_type="SPRINT_INVOICE_FAILED",
            actor=actor,
            payload={"projectKey": project_key, "dedupKey": dedup_key, "error": str(exc)},
        )
        return {"status": "failed", "warning": str(exc)}

    status = "pending_approval" if billing.approval_required else (
        "draft_created" if str(invoice.get("invoiceStatus") or "") == "draft" else "created"
    )
    result = {"status": status, **invoice}
    _patch_sprint_memory(
        project_key=project_key,
        memory_patch={
            "lastSprintInvoiceKey": dedup_key,
            "lastSprintInvoiceId": invoice.get("invoiceId"),
            "lastSprintInvoiceUrl": invoice.get("invoiceUrl"),
            "lastSprintInvoicePdfUrl": invoice.get("invoicePdfUrl"),
            "lastSprintInvoiceStatus": invoice.get("invoiceStatus"),
            "lastSprintInvoiceTotalCents": invoice.get("invoiceTotalCents"),
            "lastSprintInvoiceCurrency": invoice.get("invoiceCurrency"),
        },
    )
    EventStore().append(
        event_type="SPRINT_INVOICE_CREATED",
        actor=actor,
        payload={
            "projectKey": project_key,
            "dedupKey": dedup_key,
            "invoiceId": invoice.get("invoiceId"),
            "invoiceStatus": invoice.get("invoiceStatus"),
            "invoiceTotalCents": invoice.get("invoiceTotalCents"),
            "invoiceCurrency": invoice.get("invoiceCurrency"),
        },
    )
    return result
```

- [ ] **Step 4: Call billing before composing report**

Inside `publish_sprint_report`, after the `already_published_report` check and before `compose = reporter or _default_compose`, add:

```python
    billing_result = _create_or_reuse_sprint_invoice(
        project_key=project_key,
        snapshot=snapshot,
        dedup_key=dedup_key,
        memory=memory,
        actor=actor,
        billing_agent=billing_agent,
        invoice_creator=invoice_creator,
    )
    snapshot = dict(snapshot)
    snapshot["billing"] = {
        "status": billing_result.get("status"),
        "invoiceId": billing_result.get("invoiceId"),
        "invoiceUrl": billing_result.get("invoiceUrl"),
        "invoiceStatus": billing_result.get("invoiceStatus"),
        "invoiceTotalCents": billing_result.get("invoiceTotalCents"),
        "invoiceCurrency": billing_result.get("invoiceCurrency"),
        "warning": billing_result.get("warning"),
    }
```

Extend the returned success payload:

```python
        "billingStatus": billing_result.get("status"),
        "billingWarning": billing_result.get("warning"),
        "invoiceId": billing_result.get("invoiceId"),
        "invoiceUrl": billing_result.get("invoiceUrl"),
        "invoiceStatus": billing_result.get("invoiceStatus"),
        "invoiceTotalCents": billing_result.get("invoiceTotalCents"),
        "invoiceCurrency": billing_result.get("invoiceCurrency"),
```

- [ ] **Step 5: Run sprint report tests**

Run:

```bash
pytest tests/delivery_runtime/test_sprint_report.py tests/delivery_runtime/test_sprint_invoice.py tests/delivery_runtime/test_sprint_invoice_validation.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add delivery_runtime/pm_inbox/sprint_report.py tests/delivery_runtime/test_sprint_report.py
git commit -m "feat: attach Stripe invoices to sprint reports"
```

## Task 7: Reporter Prompt Billing Awareness

**Files:**
- Modify: `lc_server/agent_bridge/hermes_sprint_reporter.py`
- Modify: `tests/lc_server/test_external_skills_prompt_injection.py`

- [ ] **Step 1: Write failing reporter prompt test**

Append to `tests/lc_server/test_external_skills_prompt_injection.py`:

```python
def test_sprint_reporter_system_prompt_mentions_billing_links():
    from lc_server.agent_bridge.hermes_sprint_reporter import SPRINT_REPORTER_SYSTEM_PROMPT

    assert "billing.invoiceUrl" in SPRINT_REPORTER_SYSTEM_PROMPT
    assert "invoice warning" in SPRINT_REPORTER_SYSTEM_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/lc_server/test_external_skills_prompt_injection.py::test_sprint_reporter_system_prompt_mentions_billing_links -v
```

Expected: FAIL because the prompt does not mention billing.

- [ ] **Step 3: Update sprint reporter prompt**

In `lc_server/agent_bridge/hermes_sprint_reporter.py`, update `SPRINT_REPORTER_SYSTEM_PROMPT` rules to include billing:

```python
- If billing.invoiceUrl is present, include the Stripe invoice link in a short billing line.
- If billing.warning is present and billing.invoiceUrl is absent, include the invoice warning factually.
```

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/lc_server/test_external_skills_prompt_injection.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lc_server/agent_bridge/hermes_sprint_reporter.py tests/lc_server/test_external_skills_prompt_injection.py
git commit -m "feat: teach sprint reporter about invoice links"
```

## Task 8: API Response And Docs

**Files:**
- Modify: `delivery_runtime/api/schemas.py`
- Modify: `tests/delivery_runtime/test_automation_api.py`
- Modify: `README.md`

- [ ] **Step 1: Add failing API schema test**

Append to `tests/delivery_runtime/test_automation_api.py`:

```python
    def test_sprint_report_response_includes_billing_fields(self, monkeypatch, livingcolor_home):
        from delivery_runtime.pm_inbox.sprint_selection import persist_selected_sprint

        persist_selected_sprint(
            project_key="TVP",
            payload={
                "sprintName": "LivingColor Sprint",
                "capacityDays": 15,
                "usedDays": 1,
                "durationDays": 14,
                "overflowRisk": False,
                "warnings": [],
                "tickets": [],
            },
            memory_patch={
                "sprintNumber": 1,
                "sprintStartDate": "2026-06-17",
                "sprintEndDate": "2026-06-30",
            },
        )

        def fake_publish_sprint_report(*, project_key, force=False):
            return {
                "status": "sent",
                "dedupKey": "1:2026-06-30",
                "platform": "slack",
                "publishedAt": "2026-06-30T16:00:00+00:00",
                "messagePreview": "Sprint report",
                "billingStatus": "draft_created",
                "invoiceId": "in_123",
                "invoiceUrl": "https://invoice.stripe.com/in_123",
                "invoiceStatus": "draft",
                "invoiceTotalCents": 160000,
                "invoiceCurrency": "eur",
                "billingWarning": None,
            }

        monkeypatch.setattr(self.services.pm_inbox, "publish_sprint_report", fake_publish_sprint_report)

        response = self.client.post("/api/delivery/sprint/report", headers={"x-lc-project-key": "TVP"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["billingStatus"] == "draft_created"
        assert payload["invoiceUrl"] == "https://invoice.stripe.com/in_123"
        assert payload["invoiceTotalCents"] == 160000
```

- [ ] **Step 2: Run the API test to verify it fails**

Run:

```bash
pytest tests/delivery_runtime/test_automation_api.py::TestAutomationApi::test_sprint_report_response_includes_billing_fields -v
```

Expected: FAIL because `SprintReportResponse` does not include billing fields.

- [ ] **Step 3: Extend `SprintReportResponse`**

In `delivery_runtime/api/schemas.py`, update `SprintReportResponse`:

```python
class SprintReportResponse(BaseModel):
    status: str
    reason: str | None = None
    dedupKey: str | None = None
    platform: str | None = None
    publishedAt: str | None = None
    messagePreview: str | None = None
    error: str | None = None
    billingStatus: str | None = None
    billingWarning: str | None = None
    invoiceId: str | None = None
    invoiceUrl: str | None = None
    invoiceStatus: str | None = None
    invoiceTotalCents: int | None = None
    invoiceCurrency: str | None = None
```

- [ ] **Step 4: Document configuration and Hermes payments skills**

In `README.md`, add a short section:

````markdown
### Sprint Stripe Invoices

LivingColor can attach a Stripe invoice link to the end-of-sprint report when project billing is configured.

Project mapping example:

```yaml
BN:
  billing:
    stripe_customer_id: cus_...
    daily_rate_cents: 80000
    currency: eur
    invoice_mode: draft
    approval_required: false
    max_invoice_cents: 500000
```

Install the Hermes payments skills for the hackathon demo environment:

```bash
hermes skills install official/payments/stripe-projects
hermes skills install official/payments/mpp-agent
hermes skills install official/payments/stripe-link-cli
```

Stripe API credentials must stay outside project mapping files and prompts. Use an environment-managed or Hermes-managed credential source.
````

- [ ] **Step 5: Run API and report tests**

Run:

```bash
pytest tests/delivery_runtime/test_automation_api.py::TestAutomationApi::test_sprint_report_response_includes_billing_fields tests/delivery_runtime/test_sprint_report.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add delivery_runtime/api/schemas.py tests/delivery_runtime/test_automation_api.py README.md
git commit -m "docs: document sprint Stripe invoice setup"
```

## Final Verification

- [ ] **Step 1: Run focused Python tests**

```bash
pytest \
  tests/delivery_runtime/test_billing_config.py \
  tests/delivery_runtime/test_sprint_invoice.py \
  tests/delivery_runtime/test_sprint_invoice_validation.py \
  tests/delivery_runtime/test_sprint_report.py \
  tests/lc_server/test_hermes_sprint_billing_agent.py \
  tests/lc_server/test_stripe_billing.py \
  tests/lc_server/test_external_skills_prompt_injection.py \
  tests/delivery_runtime/test_automation_api.py::TestAutomationApi::test_sprint_report_response_includes_billing_fields \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run fast development smoke if available**

```bash
export LIVINGCOLOR_FAST_DEV=true
scripts/run_fast_dev_smoke.sh
```

Expected: PASS. If the script is unavailable or fails for unrelated dirty-tree reasons, record the exact failure in the handoff.

- [ ] **Step 3: Inspect git status**

```bash
git status --short
```

Expected: only intentional changes remain after task commits. Existing unrelated user changes may still appear and must not be reverted.
