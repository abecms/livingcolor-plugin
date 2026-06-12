"""Requeue development for post-MR merge conflict resolution."""

from __future__ import annotations

from typing import Any

from delivery_runtime.development.merge_conflicts import MergeAttemptResult
from delivery_runtime.development.phases import (
    DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION,
    WORK_ORDER_STAGE_MERGE_CONFLICT_RESOLUTION,
)
from delivery_runtime.execution_graph.scheduler import reset_node_for_retry
from delivery_runtime.persistence.db import connect, json_loads, utc_now_iso


def requeue_development_for_merge_conflicts(
    work_order_id: str,
    merge_result: MergeAttemptResult,
) -> dict[str, Any]:
    """Reset the development node for merge-conflict resolution after MR approval."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, payload_json FROM graph_nodes
            WHERE work_order_id = ? AND node_type = 'development'
            ORDER BY rowid ASC
            LIMIT 1
            """,
            (work_order_id,),
        ).fetchone()
        if not row:
            raise LookupError("Development node not found for work order")

        payload = json_loads(row["payload_json"], {})
        payload["developerPhase"] = DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION
        payload["mergeConflict"] = {
            "mergeTargetBranch": merge_result.merge_target_branch,
            "featureBranch": merge_result.feature_branch,
            "integrationBranch": payload.get("integrationBranch"),
            "conflictingFiles": list(merge_result.conflicting_files),
            "message": merge_result.message,
        }
        reset_node_for_retry(conn, str(row["id"]), payload=payload)

        now = utc_now_iso()
        conn.execute(
            """
            UPDATE work_orders
            SET status = 'running', current_stage = ?, updated_at = ?
            WHERE id = ?
            """,
            (WORK_ORDER_STAGE_MERGE_CONFLICT_RESOLUTION, now, work_order_id),
        )

    return {
        "workOrderId": work_order_id,
        "developerPhase": DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION,
        "conflictingFiles": list(merge_result.conflicting_files),
    }


def reset_pipeline_after_development_retry(conn, work_order_id: str) -> None:
    """Mark downstream nodes pending when development is retried after code review."""
    conn.execute(
        """
        UPDATE graph_nodes
        SET status = 'pending', started_at = NULL, completed_at = NULL
        WHERE work_order_id = ?
          AND node_type IN ('qa_validation', 'mr_creation', 'jira_update')
          AND status != 'pending'
        """,
        (work_order_id,),
    )
