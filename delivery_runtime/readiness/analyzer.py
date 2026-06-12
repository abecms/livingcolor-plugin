"""Readiness analysis for a single Jira ticket snapshot."""

from __future__ import annotations

from typing import Any

from delivery_runtime.readiness.project_mapping import resolve_recommended_repos
from delivery_runtime.readiness.scoring import ReadinessScoreResult, score_ticket


def analyze_ticket_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Run heuristic readiness analysis without mutating Jira or creating work orders."""
    project_key = str(snapshot.get("projectKey") or "").strip()
    if not project_key:
        key = str(snapshot.get("key") or "")
        project_key = key.split("-")[0] if "-" in key else ""

    repos = resolve_recommended_repos(project_key, snapshot)
    result: ReadinessScoreResult = score_ticket(snapshot, recommended_repos=repos)

    return {
        "readinessScore": result.score,
        "readinessStatus": result.status,
        "analysisSummary": result.summary,
        "blockers": result.blockers,
        "recommendedRepos": result.recommended_repos,
        "confidence": result.confidence,
        "jiraSnapshot": snapshot,
    }
