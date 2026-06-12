"""Tests for Phase 3D production shadow mode."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from delivery_runtime.shadow.guards import (
    check_mcp_tool,
    check_terminal_command,
    reset_shadow_audit_log,
)
from delivery_runtime.shadow.mode import is_shadow_mode
from delivery_runtime.shadow.paths import get_work_order_artifact_root
from delivery_runtime.validation.shadow_evaluation.corpus import load_shadow_fixture_corpus
from delivery_runtime.validation.shadow_evaluation.evaluation import run_shadow_evaluation

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CORPUS = FIXTURES / "live_evaluation_corpus.json"


@pytest.fixture(autouse=True)
def _shadow_env(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_SHADOW_MODE", "true")
    reset_shadow_audit_log()


def test_shadow_mode_blocks_git_push():
    violation = check_terminal_command("git push origin main")
    assert violation is not None
    assert violation.category == "git"
    assert violation.operation == "push"


def test_shadow_mode_allows_git_status():
    violation = check_terminal_command("git status")
    assert violation is None


def test_shadow_mode_blocks_jira_write_mcp():
    violation = check_mcp_tool("jira", "transition_issue")
    assert violation is not None
    assert violation.category == "jira"


def test_shadow_mode_allows_jira_read_mcp():
    violation = check_mcp_tool("jira", "search_issues")
    assert violation is None


def test_shadow_workspace_root_uses_evaluation_directory(_isolate_hermes_home):
    root = get_work_order_artifact_root("WO-847")
    assert "evaluation" in str(root)
    assert root.name == "WO-847"


def test_shadow_corpus_selects_ten_project_tickets():
    tickets = load_shadow_fixture_corpus(CORPUS)
    assert len(tickets) == 10
    assert all(ticket.project in {"AAC", "TVP", "FOOD"} for ticket in tickets)


def test_shadow_evaluation_runs_with_zero_side_effects(_isolate_hermes_home, monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_HOME", os.environ["LIVINGCOLOR_HOME"])
    report = run_shadow_evaluation(CORPUS, target_count=4)
    assert report["sideEffectFree"] is True
    assert report["comparison"]["heuristic"]["successRate"] >= 0
    assert report["comparison"]["hermes"]["successRate"] >= 0
    assert report["techLeadComfort"] in {"YES", "PARTIALLY", "NO"}
