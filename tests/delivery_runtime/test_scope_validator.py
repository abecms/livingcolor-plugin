"""Tests for Phase 3E Scope Contract validation."""

from __future__ import annotations

import pytest

from delivery_runtime.development.scope_contract import ScopeContract, build_scope_contract
from delivery_runtime.development.scope_validator import (
    compute_scope_metrics,
    validate_dev_result_scope,
    validate_patch_scope,
)


def _sample_plan() -> dict:
    return {
        "ticketUnderstanding": "Update criteria input.",
        "targetRepo": "gitlab.com/org/app",
        "implementationPlan": "1. Edit component\n2. Add test",
        "likelyImpactedFiles": ["admin/src/components/CriteresAutomatiquesInput.tsx"],
        "candidateTests": ["tests/CriteresAutomatiquesInput.test.ts"],
        "confidenceLevel": 0.82,
    }


def test_validate_patch_scope_passes_in_scope_files():
    plan = _sample_plan()
    contract = build_scope_contract("WO-17", plan)
    result = validate_patch_scope(
        contract=contract,
        approved_plan=plan,
        files_modified=["admin/src/components/CriteresAutomatiquesInput.tsx"],
        files_created=["tests/CriteresAutomatiquesInput.test.ts"],
        patch_stats={"linesAdded": 24, "linesRemoved": 6},
    )
    assert result.outcome == "PASS"
    assert result.scope_precision == 0.5
    assert result.scope_recall == 1.0


def test_validate_patch_scope_flags_forbidden_paths():
    plan = _sample_plan()
    contract = build_scope_contract("WO-17", plan)
    result = validate_patch_scope(
        contract=contract,
        approved_plan=plan,
        files_modified=["package-lock.json", "public/assets/index.js"],
        files_created=[],
        patch_stats={"linesAdded": 4000, "linesRemoved": 1200},
    )
    assert result.outcome == "SCOPE_VIOLATION"
    assert any("forbidden" in item.lower() for item in result.violations)


def test_validate_patch_scope_flags_scope_explosion_on_file_count():
    plan = _sample_plan()
    base = build_scope_contract("WO-17", plan)
    contract = ScopeContract(
        work_order_id=base.work_order_id,
        allowed_files=base.allowed_files,
        allowed_directories=base.allowed_directories,
        forbidden_paths=base.forbidden_paths,
        max_files_touched=2,
        max_lines_changed=base.max_lines_changed,
    )
    result = validate_patch_scope(
        contract=contract,
        approved_plan=plan,
        files_modified=[
            "admin/src/components/CriteresAutomatiquesInput.tsx",
            "admin/src/components/Other.tsx",
            "admin/src/components/Third.tsx",
        ],
        files_created=[],
        patch_stats={"linesAdded": 10, "linesRemoved": 2},
    )
    assert result.outcome == "SCOPE_EXPLOSION"


def test_compute_scope_metrics_precision_and_recall():
    precision, recall = compute_scope_metrics(
        ["a.ts", "b.ts"],
        ["a.ts", "c.ts"],
    )
    assert precision == 0.5
    assert recall == 0.5


def test_validate_dev_result_scope_uses_context_contract():
    plan = _sample_plan()
    contract = build_scope_contract("WO-17", plan)
    payload = validate_dev_result_scope(
        context={
            "approvedAnalysisPlan": plan,
            "scopeContract": contract.to_dict(),
            "workOrder": {"id": "WO-17"},
        },
        files_modified=["public/assets/logo.js"],
        files_created=[],
        files_deleted=[],
        patch_stats={"linesAdded": 5},
    )
    assert payload["outcome"] == "SCOPE_VIOLATION"


def test_classify_ticket_outcome_prioritizes_scope_violation():
    pytest.importorskip("delivery_runtime.validation.live_evaluation.outcomes")
    from delivery_runtime.validation.gate1_quality import evaluate_gate1_payload
    from delivery_runtime.validation.live_evaluation.metrics import TicketEvaluationResult
    from delivery_runtime.validation.live_evaluation.outcomes import classify_ticket_outcome
    from delivery_runtime.validation.patch_quality import evaluate_patch_quality

    snapshot = {"key": "BN-516", "summary": "Fix criteria", "description": "Acceptance criteria"}
    plan = _sample_plan()
    gate1 = evaluate_gate1_payload(plan, snapshot=snapshot, expected_repo="gitlab.com/org/app")
    dev_result = {
        "filesModified": ["public/assets/index.js"],
        "filesCreated": [],
        "scopeValidation": {
            "outcome": "SCOPE_VIOLATION",
            "reason": "Modified public/assets/index.js outside approved scope",
            "predictedFiles": plan["likelyImpactedFiles"],
            "touchedFiles": ["public/assets/index.js"],
            "scopePrecision": 0.0,
            "scopeRecall": 0.0,
            "violations": ["Modified forbidden path: public/assets/index.js"],
        },
        "patchStats": {"linesChanged": 12},
        "confidence": 0.4,
    }
    patch = evaluate_patch_quality(
        jira_key="BN-516",
        approved_plan=plan,
        dev_result=dev_result,
        gate_payload={"diffPreview": "+asset", "patchStats": {"linesChanged": 12}, "scopeValidation": dev_result["scopeValidation"]},
        workspace_path=None,
    )
    result = TicketEvaluationResult(
        ticket_key="BN-516",
        project="BN",
        candidate_tier="good",
        delivery_category="bug",
        outcome="FAILURE",
    )
    classified = classify_ticket_outcome(result=result, gate1=gate1, patch=patch)
    assert classified.outcome == "SCOPE_VIOLATION"
