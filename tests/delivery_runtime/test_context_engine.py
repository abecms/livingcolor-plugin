"""Context Engine unit tests."""

from __future__ import annotations

from delivery_runtime.context.acceptance import extract_acceptance_criteria
from delivery_runtime.context.pack_builder import ContextPackBuilder
from delivery_runtime.context.planner import RepoAwarePlanner
from delivery_runtime.pm_inbox.repo_architecture import merge_repo_architecture
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.persistence.db import connect
from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping


def test_extract_acceptance_criteria_from_description():
    description = "Acceptance criteria: persist OAuth tokens after callback completes."
    criteria = extract_acceptance_criteria(description, summary="OAuth callback")
    assert criteria
    assert "persist OAuth tokens" in criteria[0]


def test_context_pack_builder_resolves_repo_and_candidates(_isolate_hermes_home):
    install_phase25_project_mapping()
    builder = ContextPackBuilder()
    pack = builder.build(
        {
            "workOrder": {
                "jiraKey": "MAM-324",
                "title": "Render shows media offline",
                "description": "Acceptance criteria: no media offline on valid renders.",
            },
            "jiraSnapshot": {
                "key": "MAM-324",
                "summary": "Render shows media offline",
                "description": "Acceptance criteria: no media offline on valid renders.",
                "projectKey": "MAM",
                "issueType": "Bug",
            },
            "recommendedRepos": ["gitlab.com/afp/mam-iris-panel"],
        }
    )
    assert pack.identified_repo == "gitlab.com/afp/mam-iris-panel"
    assert pack.candidate_files
    assert any("ame_render_service.ts" in path for path in pack.candidate_files)


def test_repo_aware_planner_never_emits_unknown_or_wildcards(_isolate_hermes_home):
    install_phase25_project_mapping()
    builder = ContextPackBuilder()
    pack = builder.build(
        {
            "workOrder": {"jiraKey": "AAC-42", "title": "OAuth callback endpoint"},
            "jiraSnapshot": {
                "key": "AAC-42",
                "summary": "OAuth callback endpoint",
                "description": "Acceptance criteria: persist OAuth tokens after callback.",
                "projectKey": "AAC",
                "issueType": "Story",
            },
            "recommendedRepos": ["gitlab.com/org/app"],
        }
    )
    result = RepoAwarePlanner().plan(pack)
    assert result["needsClarification"] is False
    assert result["targetRepo"] != "unknown"
    assert result["likelyImpactedFiles"]
    assert all("/**" not in path for path in result["likelyImpactedFiles"])


def test_unresolved_repo_opens_clarification(_isolate_hermes_home):
    builder = ContextPackBuilder()
    pack = builder.build(
        {
            "workOrder": {"jiraKey": "ZZZ-1", "title": "Unknown project"},
            "jiraSnapshot": {"key": "ZZZ-1", "summary": "Unknown project", "projectKey": "ZZZ"},
            "recommendedRepos": [],
        }
    )
    result = RepoAwarePlanner().plan(pack)
    assert result["needsClarification"] is True


def test_mapped_repo_without_checkout_opens_clarification(_isolate_hermes_home):
    from delivery_runtime.context.models import ContextPack

    pack = ContextPack(
        jira_key="TVP-2254",
        jira_ticket={
            "key": "TVP-2254",
            "summary": "Rename Airship country property",
            "description": "Acceptance criteria: rename country to nom_pays.",
            "projectKey": "TVP",
            "issueType": "Story",
        },
        acceptance_criteria=["rename country to nom_pays."],
        identified_repo="tv5monde/tv5mondeplus-front",
        candidate_files=[],
        repo_structure=[],
        build_notes=["Repository tv5monde/tv5mondeplus-front mapped without local checkout_path."],
    )

    result = RepoAwarePlanner().plan(pack)

    assert result["needsClarification"] is True
    assert "checkout_path" in result["clarificationReason"]


def test_context_pack_includes_stored_repository_architecture(_isolate_hermes_home):
    install_phase25_project_mapping()
    memory = merge_repo_architecture({"projectKey": "MAM"}, project_key="MAM")
    with connect() as conn:
        pm_store.upsert_project_memory(
            conn,
            project_key="MAM",
            memory=memory,
            highlights=[],
        )

    builder = ContextPackBuilder()
    pack = builder.build(
        {
            "workOrder": {"jiraKey": "MAM-324", "title": "Render shows media offline"},
            "jiraSnapshot": {
                "key": "MAM-324",
                "summary": "Render shows media offline",
                "description": "Acceptance criteria: no media offline on valid renders.",
                "projectKey": "MAM",
                "issueType": "Bug",
            },
            "recommendedRepos": ["gitlab.com/afp/mam-iris-panel"],
        }
    )

    assert pack.repo_architecture.get("repoId") == "gitlab.com/afp/mam-iris-panel"
    assert pack.repo_structure
    result = RepoAwarePlanner().plan(pack)
    assert "Repository architecture:" in result["ticketUnderstanding"]

