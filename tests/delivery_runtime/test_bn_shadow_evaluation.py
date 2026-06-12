"""Tests for BN Hermes shadow evaluation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from delivery_runtime.validation.bn_shadow_evaluation.corpus import select_bn_shadow_corpus
from delivery_runtime.validation.bn_shadow_evaluation.preflight import run_bn_preflight
from delivery_runtime.validation.hermes_preflight import verify_hermes_runtime_credentials
from delivery_runtime.validation.live_evaluation.corpus import EvaluationTicket, load_fixture_corpus

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CORPUS = FIXTURES / "live_evaluation_corpus.json"


@pytest.fixture(autouse=True)
def _shadow_env(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_SHADOW_MODE", "true")
    monkeypatch.setenv("LIVINGCOLOR_FORCE_HERMES", "true")
    monkeypatch.setenv("LIVINGCOLOR_KEEP_WORKSPACE", "true")


def test_bn_corpus_selector_picks_three_categories():
    tickets = load_fixture_corpus(CORPUS)
    bn_tickets = [
        EvaluationTicket(
            snapshot={**ticket.snapshot, "projectKey": "BN", "key": f"BN-{index}"},
            expected_repo="gitlab.com/client/bibnum",
            candidate_tier=ticket.candidate_tier,
            delivery_category=ticket.delivery_category,
            selection_reason=ticket.selection_reason,
        )
        for index, ticket in enumerate(tickets, start=1)
    ]
    selected = select_bn_shadow_corpus(bn_tickets)
    assert len(selected) == 3
    categories = {ticket.delivery_category for ticket in selected}
    assert "bug" in categories
    assert categories.intersection({"feature", "other"})
    assert categories.intersection({"documentation", "refactoring"})


def test_bn_preflight_requires_env_and_mapping(tmp_path, monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_SHADOW_MODE", raising=False)
    monkeypatch.delenv("LIVINGCOLOR_FORCE_HERMES", raising=False)
    monkeypatch.delenv("LIVINGCOLOR_KEEP_WORKSPACE", raising=False)
    monkeypatch.setenv("LIVINGCOLOR_HOME", str(tmp_path / "home"))
    result = run_bn_preflight()
    assert result.ok is False
    assert any("LIVINGCOLOR_SHADOW_MODE" in item for item in result.blocking_errors)


def test_bn_preflight_accepts_checkout_override(tmp_path, monkeypatch):
    checkout = tmp_path / "bibnum"
    checkout.mkdir()
    monkeypatch.setenv("LIVINGCOLOR_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "delivery_runtime.validation.bn_shadow_evaluation.preflight._verify_jira_connection",
        lambda: (True, "ok"),
    )
    monkeypatch.setattr(
        "delivery_runtime.validation.bn_shadow_evaluation.preflight.verify_hermes_runtime_credentials",
        lambda: type("R", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
    )
    result = run_bn_preflight(bn_checkout_path=str(checkout), bn_repo_id="gitlab.com/client/bibnum")
    assert result.ok is True
    assert result.bn_mapping is not None
    assert result.bn_mapping["checkoutPath"] == str(checkout.resolve())


def test_hermes_preflight_uses_runtime_resolution(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.runtime_provider.resolve_runtime_provider",
        lambda **kwargs: {"api_key": "test-key", "provider": "openrouter"},
    )
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"model": {"provider": "openrouter", "default": "test/model"}},
    )
    result = verify_hermes_runtime_credentials()
    assert result.ok is True
    assert result.provider == "openrouter"
