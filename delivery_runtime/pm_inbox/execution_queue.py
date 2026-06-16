"""Execution queue builder for the LivingColor development scheduler."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from delivery_runtime.pm_inbox.priority import compute_priority_score


@dataclass(frozen=True)
class ExecutionQueueItem:
    readiness_id: str
    jira_key: str
    title: str
    queue_status: str
    priority_score: float
    estimated_days: float | None
    complexity: str | None
    confidence: float | None
    blockers: list[str]
    position: int
    recommended_next: bool
    priority_factors: dict[str, float]


@dataclass(frozen=True)
class ExecutionQueueSnapshot:
    project_key: str
    recommended_next: ExecutionQueueItem | None
    items: list[ExecutionQueueItem]
    executable_count: int
    blocked_count: int


def _queue_status(readiness_status: str) -> str:
    if readiness_status == "ready":
        return "executable"
    if readiness_status == "analysis_failed":
        return "blocked"
    if readiness_status == "needs_clarification":
        return "blocked"
    if readiness_status == "not_development":
        return "not_development"
    return "blocked"


def build_execution_queue(
    *,
    project_key: str,
    tickets: list[dict[str, Any]],
    project_memory: dict[str, Any] | None = None,
) -> ExecutionQueueSnapshot:
    """Order all project tickets for the execution queue."""
    memory = project_memory or {}
    ranked: list[ExecutionQueueItem] = []

    for ticket in tickets:
        snapshot = ticket.get("jiraSnapshot") or {}
        readiness_status = str(ticket.get("readinessStatus") or "blocked")
        blockers = list(ticket.get("blockers") or [])
        estimation = ticket.get("estimation") or {}
        estimated_days = estimation.get("estimatedDays")
        complexity = estimation.get("complexity")
        confidence = estimation.get("confidence")
        queue_status = _queue_status(readiness_status)

        if queue_status == "executable":
            score_result = compute_priority_score(
                snapshot=snapshot,
                readiness_score=int(ticket.get("readinessScore") or 0),
                estimated_days=float(estimated_days or 1.0),
                confidence=float(confidence or 0.0),
                readiness_status=readiness_status,
                blockers=blockers,
                project_memory=memory,
            )
            priority_score = score_result.score
            factors = score_result.factors
        else:
            priority_score = 0.0
            factors = {}

        ranked.append(
            ExecutionQueueItem(
                readiness_id=str(ticket["readinessId"]),
                jira_key=str(ticket["jiraKey"]),
                title=str(ticket.get("title") or snapshot.get("summary") or ticket["jiraKey"]),
                queue_status=queue_status,
                priority_score=priority_score,
                estimated_days=float(estimated_days) if estimated_days is not None else None,
                complexity=str(complexity) if complexity else None,
                confidence=float(confidence) if confidence is not None else None,
                blockers=blockers,
                position=0,
                recommended_next=False,
                priority_factors=factors,
            )
        )

    executable = sorted(
        [item for item in ranked if item.queue_status == "executable"],
        key=lambda row: (-row.priority_score, row.estimated_days or 999),
    )
    blocked = sorted(
        [item for item in ranked if item.queue_status == "blocked"],
        key=lambda row: row.jira_key,
    )
    non_dev = sorted(
        [item for item in ranked if item.queue_status == "not_development"],
        key=lambda row: row.jira_key,
    )

    ordered = executable + blocked + non_dev
    recommended_next = executable[0] if executable else None
    final_items: list[ExecutionQueueItem] = []
    for index, item in enumerate(ordered, start=1):
        final_items.append(
            ExecutionQueueItem(
                readiness_id=item.readiness_id,
                jira_key=item.jira_key,
                title=item.title,
                queue_status=item.queue_status,
                priority_score=item.priority_score,
                estimated_days=item.estimated_days,
                complexity=item.complexity,
                confidence=item.confidence,
                blockers=item.blockers,
                position=index,
                recommended_next=recommended_next is not None and item.jira_key == recommended_next.jira_key,
                priority_factors=item.priority_factors,
            )
        )

    return ExecutionQueueSnapshot(
        project_key=project_key,
        recommended_next=next((item for item in final_items if item.recommended_next), None),
        items=final_items,
        executable_count=len(executable),
        blocked_count=len(blocked) + len(non_dev),
    )


def execution_queue_to_dict(snapshot: ExecutionQueueSnapshot) -> dict[str, Any]:
    return {
        "projectKey": snapshot.project_key,
        "recommendedNext": asdict(snapshot.recommended_next) if snapshot.recommended_next else None,
        "items": [asdict(item) for item in snapshot.items],
        "executableCount": snapshot.executable_count,
        "blockedCount": snapshot.blocked_count,
    }
