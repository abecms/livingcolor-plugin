"""Effort estimation heuristics for daily delivery analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TicketEstimation:
    complexity: str
    estimated_days: float
    confidence: float


def estimate_ticket_effort(snapshot: dict[str, Any], *, readiness_score: int, confidence: float) -> TicketEstimation:
    """Estimate complexity and effort from ticket snapshot and readiness score."""
    description = str(snapshot.get("description") or "")
    issue_type = str(snapshot.get("issueType") or snapshot.get("issue_type") or "").lower()
    story_points = snapshot.get("storyPoints") or snapshot.get("story_points")

    base_days = 1.0
    if isinstance(story_points, (int, float)) and story_points > 0:
        base_days = max(0.5, float(story_points) * 0.5)
    elif issue_type == "bug":
        base_days = 0.75
    elif len(description) > 1200:
        base_days = 2.5
    elif len(description) > 600:
        base_days = 1.5

    if readiness_score >= 85:
        complexity = "Low"
        multiplier = 0.85
    elif readiness_score >= 70:
        complexity = "Medium"
        multiplier = 1.0
    else:
        complexity = "High"
        multiplier = 1.35

    estimated_days = round(max(0.25, base_days * multiplier), 2)
    est_confidence = round(min(0.95, max(0.45, confidence * 0.85 + readiness_score / 500)), 2)

    return TicketEstimation(
        complexity=complexity,
        estimated_days=estimated_days,
        confidence=est_confidence,
    )
