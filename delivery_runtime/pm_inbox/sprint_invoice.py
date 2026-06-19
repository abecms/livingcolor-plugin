"""Sprint invoice proposal and validation helpers."""

from __future__ import annotations

from typing import Any


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
    dedup_key = f"{sprint_number}:{sprint_end_date}"

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


def _as_ticket_keys(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_ticket_key(item) for item in value if _ticket_key(item)]


def _line_quantity(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise SprintInvoiceError("Line item quantityDays must be numeric") from None
    if parsed <= 0:
        raise SprintInvoiceError("Line item quantityDays must be positive")
    return parsed


def _line_unit_amount(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise SprintInvoiceError("Line item unitAmountCents must be numeric") from None
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
