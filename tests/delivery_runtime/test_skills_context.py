from __future__ import annotations


def test_render_skills_context_contains_stack_tracker_vcs_and_delivery_context():
    from delivery_runtime.context.models import ContextPack
    from delivery_runtime.context.skills_context import render_skills_context_markdown

    pack = ContextPack(
        jira_key="BN-42",
        jira_ticket={
            "key": "BN-42",
            "summary": "Fix search result rendering",
            "description": "Acceptance criteria: results render without duplicate cards.",
            "projectKey": "BN",
            "issueType": "Bug",
        },
        acceptance_criteria=["results render without duplicate cards."],
        identified_repo="github.com/acme/search-ui",
        repo_structure=["package.json", "src/search/results.tsx", "tests/search/results.test.tsx"],
        candidate_files=["src/search/results.tsx"],
        project_conventions=["Use React Testing Library for component tests"],
        git_history=[{"file": "src/search/results.tsx", "sha": "abcdef123456", "message": "fix search layout"}],
        repo_architecture={
            "summary": "github.com/acme/search-ui uses Node.js, React, TypeScript.",
            "stack": ["Node.js", "React", "TypeScript", "Vitest"],
            "topLevelDirectories": [{"path": "src/", "role": "Application source code"}],
            "entryPoints": ["src/main.tsx"],
            "testDirectories": ["tests/"],
            "architectureNotes": ["Application routes live under src/search."],
        },
        vcs_provider="github",
    )

    rendered = render_skills_context_markdown(pack)

    assert "## Project Stack" in rendered
    assert "Node.js, React, TypeScript, Vitest" in rendered
    assert "## Ticket Tracker" in rendered
    assert "tracker: jira" in rendered
    assert "## VCS" in rendered
    assert "vcs: github" in rendered
    assert "## Delivery Context" in rendered
    assert "BN-42" in rendered
    assert "`src/search/results.tsx`" in rendered


def test_pack_builder_populates_skills_context_and_vcs(_isolate_hermes_home):
    from delivery_runtime.context.pack_builder import ContextPackBuilder
    from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping

    install_phase25_project_mapping()

    pack = ContextPackBuilder().build(
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

    assert pack.vcs_provider == "gitlab"
    assert "## Project Stack" in pack.skills_context_markdown
    assert "tracker: jira" in pack.skills_context_markdown
    assert "vcs: gitlab" in pack.skills_context_markdown


def test_planner_user_prompt_includes_external_skills_context():
    from delivery_runtime.context.models import ContextPack
    from delivery_runtime.context.planner_prompt import build_planner_user_prompt

    pack = ContextPack(
        jira_key="BN-42",
        jira_ticket={
            "key": "BN-42",
            "summary": "Fix search result rendering",
            "description": "Acceptance criteria: results render without duplicate cards.",
            "projectKey": "BN",
            "issueType": "Bug",
        },
        acceptance_criteria=["results render without duplicate cards."],
        identified_repo="github.com/acme/search-ui",
    )
    pack.skills_context_markdown = "## Project Stack\n\nStack: React"

    prompt = build_planner_user_prompt(pack)

    assert "## External skills context" in prompt
    assert "Use this context when applying generic LivingColor role skills." in prompt
    assert "## Project Stack" in prompt
