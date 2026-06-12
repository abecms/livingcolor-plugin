"""Heuristic readiness scoring for Jira tickets (MVP)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from delivery_runtime.readiness.ticket_quality import has_acceptance_criteria

SUITABLE_ISSUE_TYPES = {"story", "task", "bug", "sub-task", "subtask", "improvement"}


@dataclass(frozen=True)
class ReadinessScoreResult:
    score: int
    status: str
    blockers: list[str]
    recommended_repos: list[str]
    confidence: float
    summary: str


def score_ticket(snapshot: dict[str, Any], *, recommended_repos: list[str] | None = None) -> ReadinessScoreResult:
    """Score a ticket snapshot using the MVP heuristic from the product spec."""
    blockers: list[str] = []
    score = 0
    repos = recommended_repos or []

    title = str(snapshot.get("summary") or snapshot.get("title") or "").strip()
    description = str(snapshot.get("description") or "").strip()

    if len(title) >= 5 and len(description) >= 20:
        score += 25
    elif len(title) >= 3:
        score += 12
        blockers.append("Description is too short or missing context")
    else:
        blockers.append("Title and description are insufficient")

    if description and has_acceptance_criteria(
        description,
        issue_type=str(snapshot.get("issueType") or snapshot.get("issue_type") or ""),
        summary=title,
    ):
        score += 30
    else:
        blockers.append("Acceptance criteria not found in the ticket")

    if repos:
        score += 25
    else:
        blockers.append("Target repository could not be resolved")

    status_text = str(snapshot.get("status") or "").lower()
    if "block" not in status_text:
        score += 10
    else:
        blockers.append("Ticket appears blocked in Jira")

    issue_type = str(snapshot.get("issueType") or snapshot.get("issue_type") or "").strip().lower()
    if issue_type in SUITABLE_ISSUE_TYPES:
        score += 10
    elif issue_type:
        blockers.append(f"Issue type '{issue_type}' may not be suitable for autonomous delivery")
    else:
        score += 5

    score = max(0, min(100, score))
    readiness_status = "ready" if score >= 70 and not blockers else "not_ready"
    confidence = round(score / 100.0, 2)
    summary = build_analysis_summary(snapshot, score, blockers, repos, readiness_status)

    return ReadinessScoreResult(
        score=score,
        status=readiness_status,
        blockers=blockers,
        recommended_repos=repos,
        confidence=confidence,
        summary=summary,
    )


def build_analysis_summary(
    snapshot: dict[str, Any],
    score: int,
    blockers: list[str],
    repos: list[str],
    readiness_status: str,
) -> str:
    key = snapshot.get("key") or snapshot.get("jiraKey") or "Ticket"
    title = snapshot.get("summary") or snapshot.get("title") or "Untitled"
    repo_text = repos[0] if repos else "unknown repository"
    if readiness_status == "ready":
        return (
            f"{key} looks ready for delivery. The ticket is understandable, scoped for {repo_text}, "
            f"and scored {score}/100."
        )
    blocker_text = blockers[0] if blockers else "Additional clarification is required"
    return f"{key} ({title}) is not ready yet ({score}/100). Primary blocker: {blocker_text}."
