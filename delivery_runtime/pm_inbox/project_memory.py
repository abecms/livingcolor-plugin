"""Project memory for the LivingColor development scheduler."""

from __future__ import annotations

from collections import Counter
from typing import Any

from delivery_runtime.persistence.db import connect, json_loads


def _jira_prefix(project_key: str) -> str:
    return f"{project_key.strip().upper()}-"


def collect_project_memory(*, project_key: str) -> dict[str, Any]:
    """Aggregate durable project memory from delivery history."""
    prefix = _jira_prefix(project_key)
    with connect() as conn:
        completed_rows = conn.execute(
            """
            SELECT jira_key, title, updated_at
            FROM work_orders
            WHERE jira_key LIKE ? AND status = 'completed'
            ORDER BY updated_at DESC
            LIMIT 100
            """,
            (f"{prefix}%",),
        ).fetchall()
        active_rows = conn.execute(
            """
            SELECT jira_key, title, current_stage, status
            FROM work_orders
            WHERE jira_key LIKE ? AND status NOT IN ('completed', 'cancelled', 'failed')
            ORDER BY updated_at DESC
            """,
            (f"{prefix}%",),
        ).fetchall()
        estimation_rows = conn.execute(
            """
            SELECT te.jira_key, te.estimated_days, te.confidence, te.complexity
            FROM ticket_estimations te
            INNER JOIN readiness_records rr ON rr.id = te.readiness_id
            WHERE rr.project_key = ?
            ORDER BY te.created_at DESC
            LIMIT 200
            """,
            (project_key,),
        ).fetchall()
        rejected_gates = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM gates g
            INNER JOIN work_orders wo ON wo.id = g.work_order_id
            WHERE wo.jira_key LIKE ? AND g.status = 'rejected'
            """,
            (f"{prefix}%",),
        ).fetchone()

    titles = [str(row["title"] or row["jira_key"]) for row in completed_rows]
    token_counter: Counter[str] = Counter()
    for title in titles:
        for token in title.lower().replace("/", " ").replace("-", " ").split():
            if len(token) >= 5:
                token_counter[token] += 1

    recurring_modules = [token for token, count in token_counter.most_common(5) if count >= 2]
    avg_confidence = 0.0
    if estimation_rows:
        avg_confidence = round(
            sum(float(row["confidence"]) for row in estimation_rows) / len(estimation_rows),
            2,
        )

    return {
        "projectKey": project_key,
        "completedTickets": len(completed_rows),
        "activeDevelopments": len(active_rows),
        "recentCompleted": [
            {"jiraKey": row["jira_key"], "title": row["title"], "completedAt": row["updated_at"]}
            for row in completed_rows[:5]
        ],
        "recurringModules": recurring_modules,
        "averageEstimationConfidence": avg_confidence,
        "rejectedPatches": int(rejected_gates["count"] if rejected_gates else 0),
        "estimationSamples": len(estimation_rows),
    }


def build_project_memory_highlights(memory: dict[str, Any]) -> list[dict[str, Any]]:
    """Return short UI highlights derived from project memory."""
    highlights: list[dict[str, Any]] = []
    completed = int(memory.get("completedTickets") or 0)
    if completed:
        highlights.append(
            {
                "label": "Tickets delivered",
                "value": str(completed),
                "detail": "Completed through LivingColor delivery",
            }
        )

    recurring = memory.get("recurringModules") or []
    if recurring:
        highlights.append(
            {
                "label": "Recurring modules",
                "value": ", ".join(str(item) for item in recurring[:3]),
                "detail": "Patterns used to improve prioritization",
            }
        )

    confidence = memory.get("averageEstimationConfidence")
    if confidence:
        highlights.append(
            {
                "label": "Estimation confidence",
                "value": f"{int(float(confidence) * 100)}%",
                "detail": "Historical average across recent estimates",
            }
        )

    rejected = int(memory.get("rejectedPatches") or 0)
    if rejected:
        highlights.append(
            {
                "label": "Rejected patches",
                "value": str(rejected),
                "detail": "Human gates that sent work back for revision",
            }
        )

    architecture = memory.get("repositoryArchitecture") or {}
    if isinstance(architecture, dict) and architecture.get("repoId"):
        stack = architecture.get("stack") or []
        highlights.append(
            {
                "label": "Repository architecture",
                "value": str(architecture.get("repoId")),
                "detail": ", ".join(str(item) for item in stack[:4]) or str(architecture.get("summary") or ""),
            }
        )

    return highlights


def load_existing_memory(*, project_key: str) -> dict[str, Any]:
    from delivery_runtime.pm_inbox import store as pm_store

    row = pm_store.get_project_memory(project_key=project_key)
    if not row:
        return {}
    return row.get("memory") or {}
