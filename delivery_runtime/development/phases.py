"""Developer agent execution phases (invariant per Work Order stage)."""

from __future__ import annotations

DEVELOPER_PHASE_IMPLEMENT = "implement"
DEVELOPER_PHASE_CODE_QUALITY_REVIEW = "code_quality_review"
DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION = "merge_conflict_resolution"

# Work-order current_stage value when merge-conflict resolution is active.
WORK_ORDER_STAGE_MERGE_CONFLICT_RESOLUTION = DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION

VALID_DEVELOPER_PHASES = frozenset(
    {
        DEVELOPER_PHASE_IMPLEMENT,
        DEVELOPER_PHASE_CODE_QUALITY_REVIEW,
        DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION,
    }
)


def normalize_developer_phase(value: str | None) -> str:
    phase = (value or DEVELOPER_PHASE_IMPLEMENT).strip().lower()
    if phase not in VALID_DEVELOPER_PHASES:
        return DEVELOPER_PHASE_IMPLEMENT
    return phase
