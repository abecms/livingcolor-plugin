"""Tests for repository architecture profiling."""

from __future__ import annotations

from delivery_runtime.context.repo_architecture import (
    analyze_repository_architecture,
    architecture_profile_is_current,
    format_architecture_for_prompt,
)
from delivery_runtime.pm_inbox.repo_architecture import ensure_project_repo_architecture, merge_repo_architecture
from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping


def test_analyze_repository_architecture_for_fixture_repo(_isolate_hermes_home):
    install_phase25_project_mapping()
    mapping_path = install_phase25_project_mapping()
    assert mapping_path.exists()

    from delivery_runtime.readiness.project_mapping import load_project_mapping

    project_cfg = load_project_mapping()["MAM"]
    checkout_path = project_cfg["repos"]["gitlab.com/afp/mam-iris-panel"]["checkout_path"]

    profile = analyze_repository_architecture(
        checkout_path,
        repo_id="gitlab.com/afp/mam-iris-panel",
    )

    assert profile["repoId"] == "gitlab.com/afp/mam-iris-panel"
    assert profile["structurePreview"]
    assert profile["summary"]
    assert architecture_profile_is_current(
        profile,
        repo_id="gitlab.com/afp/mam-iris-panel",
        checkout_path=checkout_path,
    )


def test_merge_repo_architecture_persists_profile(_isolate_hermes_home):
    install_phase25_project_mapping()

    memory = merge_repo_architecture({"projectKey": "MAM"}, project_key="MAM")
    architecture = memory.get("repositoryArchitecture")

    assert isinstance(architecture, dict)
    assert architecture.get("repoId") == "gitlab.com/afp/mam-iris-panel"
    assert architecture.get("analyzedAt")

    cached = ensure_project_repo_architecture(project_key="MAM")
    assert cached
    assert cached.get("repoId") == architecture.get("repoId")
    assert architecture_profile_is_current(
        cached,
        repo_id=str(architecture.get("repoId")),
        checkout_path=str(architecture.get("checkoutPath")),
    )


def test_format_architecture_for_prompt_includes_summary(_isolate_hermes_home):
    install_phase25_project_mapping()
    profile = ensure_project_repo_architecture(project_key="MAM")
    assert profile

    rendered = format_architecture_for_prompt(profile)
    assert "Repository:" in rendered
    assert profile["summary"] in rendered
