"""Tests for Phase 3C live delivery evaluation."""

from __future__ import annotations

from pathlib import Path

from delivery_runtime.validation.live_evaluation.aggregates import evaluate_go_no_go, summarize_product_metrics
from delivery_runtime.validation.live_evaluation.corpus import classify_ticket, load_fixture_corpus, select_balanced_corpus
from delivery_runtime.validation.live_evaluation.evaluation import run_live_delivery_evaluation
from delivery_runtime.validation.live_evaluation.outcomes import classify_ticket_outcome
from delivery_runtime.validation.live_evaluation.metrics import TicketEvaluationResult
from delivery_runtime.validation.gate1_quality import evaluate_gate1_payload
from delivery_runtime.validation.patch_quality import evaluate_patch_quality


FIXTURES = Path(__file__).resolve().parent / "fixtures"
CORPUS = FIXTURES / "live_evaluation_corpus.json"


def test_corpus_has_at_least_twenty_tickets():
    tickets = load_fixture_corpus(CORPUS)
    assert len(tickets) >= 20


def test_ticket_classification_covers_tiers():
    tickets = load_fixture_corpus(CORPUS)
    tiers = {ticket.candidate_tier for ticket in tickets}
    categories = {ticket.delivery_category for ticket in tickets}
    assert "good" in tiers
    assert "medium" in tiers
    assert "hard" in tiers
    assert "bug" in categories
    assert "feature" in categories or "other" in categories


def test_select_balanced_corpus_respects_bounds():
    tickets = load_fixture_corpus(CORPUS)
    selected = select_balanced_corpus(tickets, min_tickets=20, max_tickets=24)
    assert 20 <= len(selected) <= 24


def test_classify_epic_as_hard_candidate():
    tier, category, _reason = classify_ticket(
        {
            "key": "TVP-403",
            "summary": "Epic architecture migration",
            "description": "multi-repository infrastructure migration",
            "issueType": "Epic",
        }
    )
    assert tier == "hard"
    assert category == "epic"


def test_live_evaluation_runs_end_to_end(_isolate_hermes_home):
    report = run_live_delivery_evaluation(
        CORPUS,
        min_tickets=8,
        max_tickets=8,
        developer_backend="heuristic",
    )
    assert report["summary"]["totalTickets"] == 8
    assert report["results"]
    assert report["goNoGo"] in {"GO", "NO GO"}
    assert report["pmValue"] in {"YES", "PARTIALLY", "NO"}
    assert report["markdown"].startswith("# Live Delivery Evaluation Report")


def test_outcome_success_requires_good_patch_and_passing_checks():
    snapshot = {"key": "AAC-101", "summary": "OAuth callback", "description": "Acceptance criteria: persist token"}
    gate_payload = {
        "ticketUnderstanding": "AAC-101 targets OAuth callback.",
        "targetRepo": "gitlab.com/org/app",
        "implementationPlan": "1. Inspect `src/auth/oauth_callback.ts`\n2. Add test\n3. Document",
        "likelyImpactedFiles": ["src/auth/oauth_callback.ts"],
        "risks": ["OAuth token persistence needs regression coverage"],
        "confidenceLevel": 0.82,
    }
    gate1 = evaluate_gate1_payload(gate_payload, snapshot=snapshot, expected_repo="gitlab.com/org/app")
    patch = evaluate_patch_quality(
        jira_key="AAC-101",
        approved_plan=gate_payload,
        dev_result={
            "filesModified": ["src/auth/oauth_callback.ts"],
            "filesCreated": ["tests/test_delivery_aac_101.py"],
            "diffPreview": "+export function deliveryFix() {}",
            "patchStats": {"linesChanged": 12},
            "confidence": 0.84,
            "scopeValidation": {
                "outcome": "PASS",
                "reason": "Patch stayed within the Scope Contract.",
                "predictedFiles": ["src/auth/oauth_callback.ts"],
                "touchedFiles": ["src/auth/oauth_callback.ts", "tests/test_delivery_aac_101.py"],
                "scopePrecision": 0.5,
                "scopeRecall": 1.0,
                "violations": [],
            },
        },
        gate_payload={"diffPreview": "+export function deliveryFix() {}", "patchStats": {"linesChanged": 12}},
        workspace_path=None,
    )
    result = TicketEvaluationResult(
        ticket_key="AAC-101",
        project="AAC",
        candidate_tier="good",
        delivery_category="bug",
        outcome="FAILURE",
    )
    classified = classify_ticket_outcome(result=result, gate1=gate1, patch=patch)
    assert classified.outcome == "SUCCESS"
