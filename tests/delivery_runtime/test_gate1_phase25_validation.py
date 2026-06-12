"""Phase 2.5 Gate 1 quality validation tests."""

from __future__ import annotations

from pathlib import Path

from delivery_runtime.validation.gate1_quality import evaluate_gate1_payload
from delivery_runtime.validation.phase25_runner import load_fixture_cases, run_gate1_validation_case, summarize_results


FIXTURES = Path(__file__).parent / "fixtures" / "gate1_phase25_jira_live.json"


def test_fixture_corpus_runs_end_to_end(_isolate_hermes_home):
    cases = load_fixture_cases(FIXTURES)
    assert len(cases) >= 5
    results = [run_gate1_validation_case(case) for case in cases]
    report = summarize_results(results)
    assert report["summary"]["cases"] == len(cases)
    assert report["summary"]["rejectCases"] >= 2


def test_evaluator_flags_generic_wildcard_files():
    snapshot = {"key": "AAC-1", "summary": "OAuth callback", "description": "Acceptance criteria: store token"}
    payload = {
        "ticketUnderstanding": "The ticket AAC-1 (OAuth callback) asks to deliver: Acceptance criteria: store token.",
        "targetRepo": "gitlab.com/org/app",
        "implementationPlan": (
            "1. Confirm scope for AAC-1 against acceptance criteria.\n"
            "2. Inspect repository gitlab.com/org/app and locate the integration points.\n"
            "3. Implement the smallest change that satisfies the ticket."
        ),
        "likelyImpactedFiles": ["gitlab.com/org/app/src/**"],
        "risks": ["No major risks identified by the planning agent."],
        "confidenceLevel": 0.82,
    }
    assessment = evaluate_gate1_payload(payload, snapshot=snapshot, expected_repo="gitlab.com/org/app")
    assert assessment.repo_correct == "oui"
    assert assessment.plan_actionable == "non"
    assert assessment.plan_quality in {"moyen", "mauvais"}


def test_evaluator_detects_feedback_in_revised_plan():
    snapshot = {"key": "AAC-9", "summary": "OAuth callback", "description": "Acceptance criteria: store token"}
    payload = {
        "ticketUnderstanding": "Previous review feedback to address: Add migration plan",
        "targetRepo": "gitlab.com/org/app",
        "implementationPlan": "2. Incorporate reviewer feedback: Add migration plan",
        "likelyImpactedFiles": ["src/auth/callback.ts"],
        "risks": ["Missing migration plan"],
        "confidenceLevel": 0.77,
    }
    assessment = evaluate_gate1_payload(
        payload,
        snapshot=snapshot,
        expected_repo="gitlab.com/org/app",
        prior_feedback="Add migration plan",
    )
    assert assessment.feedback_incorporated == "oui"
