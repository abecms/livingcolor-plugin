"""Deterministic sprint invoice proposal for cloud/heuristic runs."""

from __future__ import annotations

from typing import Any


def propose_heuristic_sprint_billing(billing_snapshot: dict[str, Any], *, project_key: str) -> dict[str, Any]:
    """Build a Stripe invoice proposal from the billing snapshot without an LLM."""
    customer_id = str(billing_snapshot.get("customerId") or "").strip()
    currency = str(billing_snapshot.get("currency") or "eur").strip().lower()
    daily_rate = int(billing_snapshot.get("dailyRateCents") or 0)
    sprint_number = billing_snapshot.get("sprintNumber") or "?"

    line_items: list[dict[str, Any]] = []
    for ticket in billing_snapshot.get("deliveredTickets") or []:
        if not isinstance(ticket, dict):
            continue
        key = str(ticket.get("jiraKey") or "").strip().upper()
        if not key:
            continue
        try:
            quantity_days = float(ticket.get("estimatedDays") or 0)
        except (TypeError, ValueError):
            continue
        if quantity_days <= 0:
            continue
        amount_cents = int(round(quantity_days * daily_rate))
        title = str(ticket.get("title") or key).strip()
        line_items.append(
            {
                "description": f"Delivered {key}: {title}"[:120],
                "quantityDays": quantity_days,
                "unitAmountCents": daily_rate,
                "amountCents": amount_cents,
                "ticketKeys": [key],
            }
        )

    total_cents = sum(int(item.get("amountCents") or 0) for item in line_items)
    return {
        "customerId": customer_id,
        "currency": currency,
        "lineItems": line_items,
        "memo": f"Sprint {sprint_number} delivery invoice ({project_key.strip().upper()})",
        "totalCents": total_cents,
    }
