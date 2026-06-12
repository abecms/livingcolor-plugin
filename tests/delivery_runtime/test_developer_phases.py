"""Tests for developer phases and merge conflict helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

from delivery_runtime.development.merge_conflicts import (
    attempt_merge_into_target_branch,
    list_conflicting_files,
    workspace_has_merge_conflicts,
)
from delivery_runtime.development.phases import (
    DEVELOPER_PHASE_CODE_QUALITY_REVIEW,
    DEVELOPER_PHASE_IMPLEMENT,
    DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION,
    WORK_ORDER_STAGE_MERGE_CONFLICT_RESOLUTION,
    normalize_developer_phase,
)
from delivery_runtime.orchestration.engine import OrchestrationEngine
from delivery_runtime.shadow.context import allow_internal_git


def test_normalize_developer_phase_defaults_to_implement():
    assert normalize_developer_phase(None) == DEVELOPER_PHASE_IMPLEMENT
    assert normalize_developer_phase("code_quality_review") == DEVELOPER_PHASE_CODE_QUALITY_REVIEW
    assert normalize_developer_phase("unknown") == DEVELOPER_PHASE_IMPLEMENT


def test_list_conflicting_files_detects_unmerged_paths(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with allow_internal_git():
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=repo, check=True, capture_output=True)
        (repo / "README.md").write_text("feature\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-am", "feature"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)
        (repo / "README.md").write_text("main\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-am", "main"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "feature"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "merge", "main"], cwd=repo, check=False, capture_output=True)

    assert workspace_has_merge_conflicts(repo)
    assert "README.md" in list_conflicting_files(repo)


def test_attempt_merge_into_target_branch_reports_conflicts(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with allow_internal_git():
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
        (repo / "app.txt").write_text("v1\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "staging"], cwd=repo, check=True, capture_output=True)
        (repo / "app.txt").write_text("staging\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-am", "staging"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/TVP-1", "main"], cwd=repo, check=True, capture_output=True)
        (repo / "app.txt").write_text("feature\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-am", "feature"], cwd=repo, check=True, capture_output=True)

    result = attempt_merge_into_target_branch(repo)
    assert result.ok is False
    assert result.merge_target_branch == "staging"
    assert result.feature_branch == "feature/TVP-1"
    assert result.conflicting_files


def test_orchestrator_stage_for_merge_conflict_resolution():
    stage = OrchestrationEngine._stage_for_running_node(
        "development",
        node_payload={"developerPhase": DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION},
    )
    assert stage == WORK_ORDER_STAGE_MERGE_CONFLICT_RESOLUTION
