"""Priority scoring engine for the LivingColor execution queue."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

JIRA_PRIORITY_POINTS = {
    "highest": 40.0,
    "high": 32.0,
    "medium": 24.0,
    "low": 16.0,
    "lowest": 8.0,
}


@dataclass(frozen=True)
class PriorityScoreResult:
    score: float
    factors: dict[str, float]


def _parse_age_days(snapshot: dict[str, Any]) -> float:
    for field in ("ageDays", "age_days", "daysOpen", "days_open"):
        value = snapshot.get(field)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def _jira_priority_points(snapshot: dict[str, Any]) -> float:
    priority = str(snapshot.get("priority") or snapshot.get("priorityName") or "medium").lower()
    return JIRA_PRIORITY_POINTS.get(priority, 24.0)


def _business_value_points(snapshot: dict[str, Any]) -> float:
    labels = snapshot.get("labels") or []
    label_text = " ".join(str(item).lower() for item in labels)
    bonus = 0.0
    if "critical" in label_text or "blocker" in label_text:
        bonus += 8.0
    if "customer" in label_text or "production" in label_text:
        bonus += 4.0
    return bonus


def _effort_adjustment(estimated_days: float) -> float:
    if estimated_days <= 0.5:
        return 6.0
    if estimated_days <= 1.0:
        return 4.0
    if estimated_days <= 2.0:
        return 1.0
    return -4.0


def _memory_adjustment(snapshot: dict[str, Any], project_memory: dict[str, Any]) -> float:
    recurring_modules = project_memory.get("recurringModules") or []
    title = str(snapshot.get("summary") or snapshot.get("title") or "").lower()
    bonus = 0.0
    for module in recurring_modules[:5]:
        token = str(module).lower()
        if token and token in title:
            bonus += 2.0
    completed = int(project_memory.get("completedTickets") or 0)
    if completed >= 10:
        bonus += 1.0
    return min(8.0, bonus)


def compute_priority_score(
    *,
    snapshot: dict[str, Any],
    readiness_score: int,
    estimated_days: float,
    confidence: float,
    readiness_status: str,
    blockers: list[str],
    project_memory: dict[str, Any] | None = None,
) -> PriorityScoreResult:
    """Return a 0-100 execution priority score for queue ordering."""
    memory = project_memory or {}
    if readiness_status != "ready" or blockers:
        return PriorityScoreResult(score=0.0, factors={"blocked": 0.0})

    age_days = _parse_age_days(snapshot)
    age_points = min(25.0, age_days / 7.0 * 5.0)
    readiness_points = min(20.0, readiness_score / 5.0)
    confidence_points = min(10.0, confidence * 10.0)
    jira_points = _jira_priority_points(snapshot)
    business_points = _business_value_points(snapshot)
    effort_points = _effort_adjustment(estimated_days)
    memory_points = _memory_adjustment(snapshot, memory)

    factors = {
        "jiraPriority": round(jira_points, 2),
        "ticketAge": round(age_points, 2),
        "readiness": round(readiness_points, 2),
        "confidence": round(confidence_points, 2),
        "businessValue": round(business_points, 2),
        "effort": round(effort_points, 2),
        "projectMemory": round(memory_points, 2),
        "executableBase": 25.0,
    }
    total = sum(factors.values())
    return PriorityScoreResult(score=round(min(100.0, max(0.0, total)), 1), factors=factors)
