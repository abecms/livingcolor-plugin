"""Confidence scoring for explainable delivery (Phase 4B)."""

from __future__ import annotations

from typing import Any

from delivery_runtime.explainability.evidence_engine import count_ticket_references


def score_file_confidence(
    *,
    path: str,
    ticket_text: str,
    approved_plan: dict[str, Any],
    context_pack: dict[str, Any],
    code_review_payload: dict[str, Any],
    scope_validation: dict[str, Any] | None = None,
) -> float:
    """Return a 0-100 confidence score for touching this file."""
    scope_validation = scope_validation or code_review_payload.get("scopeValidation") or {}
    base = float(approved_plan.get("confidenceLevel") or 0.65) * 100

    score = base
    likely_impacted = [str(item) for item in approved_plan.get("likelyImpactedFiles") or []]
    if path in likely_impacted:
        score += 12
    elif likely_impacted and path not in likely_impacted:
        score -= 8

    candidate_files = [str(item) for item in context_pack.get("candidate_files") or []]
    if path in candidate_files:
        rank = candidate_files.index(path)
        score += max(8 - rank * 2, 2)

    references = count_ticket_references(path, ticket_text)
    score += min(references * 4, 12)

    touched = set(
        str(item)
        for item in (code_review_payload.get("filesModified") or [])
        + (code_review_payload.get("filesCreated") or [])
    )
    if path in touched:
        score += 5

    scope_outcome = str(scope_validation.get("outcome") or "")
    if scope_outcome == "PASS":
        score += 4
    elif scope_outcome and scope_outcome not in {"MISSING", ""}:
        score -= 10

    precision = scope_validation.get("scopePrecision")
    if isinstance(precision, (int, float)) and precision >= 0.9:
        score += 3

    test_run = code_review_payload.get("testRun") or {}
    if test_run.get("passed"):
        score += 3

    return _clamp(score, 35.0, 97.0)


def score_overall_confidence(file_scores: list[float], approved_plan: dict[str, Any]) -> float:
    if not file_scores:
        plan_score = float(approved_plan.get("confidenceLevel") or 0.65) * 100
        return _clamp(plan_score, 35.0, 97.0)
    average = sum(file_scores) / len(file_scores)
    peak = max(file_scores)
    blended = average * 0.7 + peak * 0.3
    return _clamp(blended, 35.0, 97.0)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
