"""Decision Trace builder for explainable MR drafts (Phase 4B)."""

from __future__ import annotations

from typing import Any

from delivery_runtime.explainability.confidence_engine import score_file_confidence, score_overall_confidence
from delivery_runtime.explainability.evidence_engine import (
    build_file_evidence,
    collect_ticket_text,
    rejected_alternatives_for_file,
)
from delivery_runtime.explainability.models import DecisionTrace, FileDecision
from delivery_runtime.explainability.risk_engine import assess_delivery_risks


def build_decision_trace(
    *,
    jira_key: str,
    jira_snapshot: dict[str, Any],
    approved_plan: dict[str, Any],
    context_pack: dict[str, Any],
    code_review_payload: dict[str, Any],
    files_modified: list[str],
    scope_validation: dict[str, Any] | None = None,
    scope_contract: dict[str, Any] | None = None,
) -> DecisionTrace:
    scope_validation = scope_validation or code_review_payload.get("scopeValidation") or {}
    ticket_text = collect_ticket_text(jira_snapshot, approved_plan)

    file_decisions: list[FileDecision] = []
    file_scores: list[float] = []
    global_rejected: list[str] = []

    for path in files_modified:
        why, evidence = build_file_evidence(
            path=path,
            ticket_text=ticket_text,
            approved_plan=approved_plan,
            context_pack=context_pack,
            code_review_payload=code_review_payload,
            scope_contract=scope_contract,
        )
        confidence = score_file_confidence(
            path=path,
            ticket_text=ticket_text,
            approved_plan=approved_plan,
            context_pack=context_pack,
            code_review_payload=code_review_payload,
            scope_validation=scope_validation,
        )
        rejected = rejected_alternatives_for_file(
            selected_path=path,
            files_modified=files_modified,
            approved_plan=approved_plan,
            context_pack=context_pack,
        )
        for alt in rejected:
            if alt not in global_rejected:
                global_rejected.append(alt)

        file_scores.append(confidence)
        file_decisions.append(
            FileDecision(
                path=path,
                why=why,
                evidence=evidence,
                confidence=confidence,
                rejected_alternatives=rejected,
                role=_file_role(path),
            )
        )

    overall = score_overall_confidence(file_scores, approved_plan)
    risk_assessment = assess_delivery_risks(
        files_modified=files_modified,
        approved_plan=approved_plan,
        code_review_payload=code_review_payload,
        scope_validation=scope_validation,
    )
    reasoning_summary = _build_reasoning_summary(
        jira_key=jira_key,
        files_modified=files_modified,
        overall_confidence=overall,
        approved_plan=approved_plan,
        scope_validation=scope_validation,
    )

    return DecisionTrace(
        reasoning_summary=reasoning_summary,
        overall_confidence=overall,
        file_decisions=file_decisions,
        rejected_alternatives=global_rejected[:8],
        risk_assessment=risk_assessment,
    )


def _build_reasoning_summary(
    *,
    jira_key: str,
    files_modified: list[str],
    overall_confidence: float,
    approved_plan: dict[str, Any],
    scope_validation: dict[str, Any],
) -> str:
    primary = files_modified[0] if files_modified else "no recorded files"
    understanding = str(approved_plan.get("ticketUnderstanding") or "").strip()
    scope_outcome = str(scope_validation.get("outcome") or "MISSING")
    lines = [
        f"{jira_key}: LivingColor selected {len(files_modified)} file(s), led by `{primary}`.",
        f"Overall confidence: {overall_confidence:.0f}%. Scope validation: {scope_outcome}.",
    ]
    if understanding:
        lines.append(understanding)
    return " ".join(lines)


def _file_role(path: str) -> str:
    lowered = path.lower()
    if any(marker in lowered for marker in ("/tests/", ".test.", ".spec.")):
        return "test"
    if any(marker in lowered for marker in (".tsx", ".jsx", "/components/")):
        return "ui"
    if any(marker in lowered for marker in ("/api/", "/routes/", "service")):
        return "service"
    return "implementation"
