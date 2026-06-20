"""Deterministic sprint retrospective message for cloud/heuristic runs."""

from __future__ import annotations

from typing import Any


def compose_heuristic_sprint_report(snapshot: dict[str, Any], *, project_key: str) -> str:
    """Build a factual sprint retrospective without an LLM."""
    key = (project_key or "").strip().upper()
    sprint = snapshot.get("sprint") or {}
    sprint_name = str(sprint.get("name") or snapshot.get("sprintName") or "Sprint")
    sprint_number = snapshot.get("sprintNumber") or sprint.get("number") or "?"
    start = sprint.get("startDate") or "?"
    end = sprint.get("endDate") or "?"
    capacity = snapshot.get("capacityDays") or sprint.get("capacityDays") or "?"
    used = snapshot.get("usedDays") or sprint.get("usedDays") or 0

    tickets = snapshot.get("tickets") or []
    work_orders = snapshot.get("workOrders") or []
    delivered = [wo for wo in work_orders if str(wo.get("status") or "").lower() == "completed"]
    lang = str(snapshot.get("communicationLanguage") or "fr").lower()
    billing = snapshot.get("billing") or {}

    if lang.startswith("fr"):
        lines = [
            f"*{sprint_name} #{sprint_number}* ({start} → {end})",
            f"Projet: *{key}*",
            f"Capacité: {used}/{capacity} j",
            f"Tickets planifiés: {len(tickets)}",
            f"Work Orders livrés: {len(delivered)}/{len(work_orders)}",
        ]
        if billing.get("invoiceUrl"):
            lines.append(f"Facture test: {billing['invoiceUrl']}")
        elif billing.get("warning"):
            lines.append(f"Facturation: {billing['warning']}")
        lines.append("_Rapport généré en mode heuristique (cloud FRT)._")
    else:
        lines = [
            f"*{sprint_name} #{sprint_number}* ({start} → {end})",
            f"Project: *{key}*",
            f"Capacity: {used}/{capacity} days",
            f"Planned tickets: {len(tickets)}",
            f"Delivered work orders: {len(delivered)}/{len(work_orders)}",
        ]
        if billing.get("invoiceUrl"):
            lines.append(f"Test invoice: {billing['invoiceUrl']}")
        elif billing.get("warning"):
            lines.append(f"Billing: {billing['warning']}")
        lines.append("_Heuristic sprint report (cloud FRT)._")

    return "\n".join(lines)
