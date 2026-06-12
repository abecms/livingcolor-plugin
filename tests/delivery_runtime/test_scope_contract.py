"""Tests for Phase 3E Scope Contract generation."""

from __future__ import annotations

from delivery_runtime.development.scope_contract import (
    DEFAULT_FORBIDDEN_PATHS,
    build_scope_contract,
    predicted_files_from_plan,
)


def test_build_scope_contract_from_gate1_plan():
    plan = {
        "likelyImpactedFiles": ["admin/src/components/CriteresAutomatiquesInput.tsx"],
        "candidateTests": ["tests/CriteresAutomatiquesInput.test.ts"],
        "implementationPlan": "1. Update component\n2. Add test",
    }
    contract = build_scope_contract("WO-17", plan)

    assert contract.work_order_id == "WO-17"
    assert "admin/src/components/CriteresAutomatiquesInput.tsx" in contract.allowed_files
    assert "tests/CriteresAutomatiquesInput.test.ts" in contract.allowed_files
    assert "admin/src/components" in contract.allowed_directories
    assert "tests" in contract.allowed_directories
    assert contract.forbidden_paths == list(DEFAULT_FORBIDDEN_PATHS)
    assert "package-lock.json" in contract.forbidden_paths
    assert contract.max_files_touched == 5
    assert contract.max_lines_changed == 200


def test_predicted_files_from_plan_uses_likely_impacted_files():
    plan = {"likelyImpactedFiles": ["src/auth/oauth_callback.ts"]}
    assert predicted_files_from_plan(plan) == ["src/auth/oauth_callback.ts"]


def test_build_scope_contract_infers_test_path_when_missing():
    plan = {
        "likelyImpactedFiles": ["admin/src/components/Widget.tsx"],
        "implementationPlan": "Adjust widget rendering.",
    }
    contract = build_scope_contract("WO-18", plan)
    assert any("test" in path for path in contract.allowed_files)
