"""Sprint recommendation planner for daily delivery analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SprintTicketCandidate:
    readiness_id: str
    jira_key: str
    title: str
    estimated_days: float
    priority_rank: int
    urgency_score: float
    warnings: list[str]


@dataclass(frozen=True)
class SprintRecommendation:
    sprint_name: str
    capacity_days: float
    used_days: float
    duration_days: int
    tickets: list[SprintTicketCandidate]
    warnings: list[str]
    overflow_risk: bool


PRIORITY_RANK = {
    "highest": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "lowest": 4,
}


def _priority_rank(snapshot: dict[str, Any]) -> int:
    priority = str(snapshot.get("priority") or snapshot.get("priorityName") or "medium").lower()
    return PRIORITY_RANK.get(priority, 2)


def _urgency_score(snapshot: dict[str, Any], *, ticket_age_days: float, estimated_days: float) -> float:
    priority_bonus = 5 - _priority_rank(snapshot)
    age_bonus = min(3.0, ticket_age_days / 7.0)
    risk_penalty = 0.5 if estimated_days >= 2.0 else 0.0
    return round(priority_bonus + age_bonus - risk_penalty, 2)


def _parse_age_days(snapshot: dict[str, Any]) -> float:
    for field in ("ageDays", "age_days", "daysOpen", "days_open"):
        value = snapshot.get(field)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def build_sprint_recommendation(
    *,
    project_key: str,
    candidates: list[dict[str, Any]],
    capacity_days: float,
    duration_days: int,
    sprint_number: int | None = None,
) -> SprintRecommendation:
    """Select an ordered LivingColor sprint backlog within capacity."""
    sprint_name = f"LivingColor Sprint {sprint_number}" if sprint_number else "LivingColor Sprint"
    ranked: list[SprintTicketCandidate] = []
    warnings: list[str] = []

    for item in candidates:
        snapshot = item.get("jiraSnapshot") or item.get("jira_snapshot") or {}
        estimated_days = float(item.get("estimatedDays") or item.get("estimated_days") or 1.0)
        age_days = _parse_age_days(snapshot)
        urgency = _urgency_score(snapshot, ticket_age_days=age_days, estimated_days=estimated_days)
        ticket_warnings: list[str] = []
        if estimated_days >= 3:
            ticket_warnings.append("Large estimate — consider splitting the ticket")
        if age_days >= 21:
            ticket_warnings.append("Ticket has been open for more than three weeks")

        ranked.append(
            SprintTicketCandidate(
                readiness_id=str(item["readinessId"]),
                jira_key=str(item["jiraKey"]),
                title=str(item.get("title") or snapshot.get("summary") or item["jiraKey"]),
                estimated_days=estimated_days,
                priority_rank=_priority_rank(snapshot),
                urgency_score=urgency,
                warnings=ticket_warnings,
            )
        )

    ranked.sort(key=lambda row: (row.priority_rank, -row.urgency_score, row.estimated_days))

    selected: list[SprintTicketCandidate] = []
    used = 0.0
    overflow_risk = False

    for ticket in ranked:
        if used + ticket.estimated_days <= capacity_days + 0.01:
            selected.append(ticket)
            used += ticket.estimated_days
            continue
        overflow_risk = True

    if overflow_risk:
        warnings.append("Some ranked tickets exceed sprint capacity")
    if not selected and ranked:
        warnings.append("No tickets fit within the configured sprint capacity")

    return SprintRecommendation(
        sprint_name=sprint_name,
        capacity_days=capacity_days,
        used_days=round(used, 2),
        duration_days=duration_days,
        tickets=selected,
        warnings=warnings,
        overflow_risk=overflow_risk,
    )
