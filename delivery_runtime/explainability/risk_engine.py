"""Structured risk assessment for explainable delivery (Phase 4B)."""

from __future__ import annotations

from delivery_runtime.explainability.evidence_engine import DB_MARKERS, API_MARKERS, UI_MARKERS, _looks_like_test_path
from delivery_runtime.explainability.models import ImpactLevel, RiskAssessment


def assess_delivery_risks(
    *,
    files_modified: list[str],
    approved_plan: dict[str, Any],
    code_review_payload: dict[str, Any],
    scope_validation: dict[str, Any] | None = None,
) -> RiskAssessment:
    scope_validation = scope_validation or code_review_payload.get("scopeValidation") or {}
    plan_risks = [str(item) for item in approved_plan.get("risks") or []]
    review_risks = [str(item) for item in code_review_payload.get("risks") or []]

    db_level = _aggregate_impact(files_modified, DB_MARKERS, test_paths=True)
    api_level = _aggregate_impact(files_modified, API_MARKERS, test_paths=True)
    ui_level = _aggregate_impact(files_modified, UI_MARKERS, test_paths=True)

    if _looks_like_test_only(files_modified):
        db_level = "none"
        api_level = "none"
        ui_level = "none"

    summary = _build_summary(db_level, api_level, ui_level)
    for risk in plan_risks + review_risks:
        cleaned = risk.strip()
        if cleaned and cleaned not in summary:
            summary.append(cleaned)

    scope_outcome = str(scope_validation.get("outcome") or "")
    if scope_outcome and scope_outcome not in {"PASS", "MISSING", ""}:
        reason = str(scope_validation.get("reason") or scope_outcome).strip()
        if reason:
            summary.insert(0, reason)

    return RiskAssessment(
        database_impact=db_level,
        api_impact=api_level,
        ui_impact=ui_level,
        summary=summary[:8],
    )


def _aggregate_impact(
    files_modified: list[str],
    markers: tuple[str, ...],
    *,
    test_paths: bool,
) -> ImpactLevel:
    hits = 0
    for path in files_modified:
        if test_paths and _looks_like_test_path(path):
            continue
        lowered = path.lower()
        if any(marker in lowered for marker in markers):
            hits += 1
    if hits == 0:
        return "none"
    if hits == 1:
        return "low"
    if hits <= 3:
        return "medium"
    return "high"


def _looks_like_test_only(files_modified: list[str]) -> bool:
    if not files_modified:
        return False
    return all(_looks_like_test_path(path) for path in files_modified)


def _build_summary(db_level: ImpactLevel, api_level: ImpactLevel, ui_level: ImpactLevel) -> list[str]:
    summary: list[str] = []
    summary.append(_impact_sentence("database", db_level))
    summary.append(_impact_sentence("API", api_level))
    summary.append(_impact_sentence("UI", ui_level))
    return summary


def _impact_sentence(area: str, level: ImpactLevel) -> str:
    if level == "none":
        return f"No {area} impact detected"
    if level == "low":
        return f"Low {area} impact — review adjacent behavior"
    if level == "medium":
        return f"Medium {area} impact — targeted regression recommended"
    return f"High {area} impact — coordinated validation required"
