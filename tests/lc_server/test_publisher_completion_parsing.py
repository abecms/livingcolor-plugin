"""Publisher agent completion parsing."""

import pytest

from lc_server.agent_bridge.hermes_publisher import (
    PublisherCompletionError,
    parse_publisher_completion,
)


def test_parses_provider_neutral_github_completion():
    text = (
        "Pushed and created the PR.\n"
        '```json\n{"reviewRequestUrl": "https://github.com/org/app/pull/42", '
        '"reviewRequestNumber": 42, "targetBranch": "main", '
        '"provider": "github", "status": "published"}\n```'
    )

    result = parse_publisher_completion(text)

    assert result["reviewRequestUrl"] == "https://github.com/org/app/pull/42"
    assert result["reviewRequestNumber"] == 42
    assert result["reviewRequestProvider"] == "github"
    assert result["mrUrl"] == "https://github.com/org/app/pull/42"
    assert result["mrIid"] == 42


def test_parses_published_block():
    text = (
        "Pushed and created the MR.\n"
        '```json\n{"mrUrl": "https://g.example/m/1", "mrIid": 1, '
        '"targetBranch": "develop", "status": "published"}\n```'
    )
    result = parse_publisher_completion(text)
    assert result["mrIid"] == 1
    assert result["status"] == "published"


def test_failed_status_raises():
    text = '```json\n{"status": "failed", "error": "push rejected"}\n```'
    with pytest.raises(PublisherCompletionError, match="push rejected"):
        parse_publisher_completion(text)


def test_missing_json_raises():
    with pytest.raises(PublisherCompletionError):
        parse_publisher_completion("done, all good!")


def test_missing_iid_raises():
    text = '```json\n{"mrUrl": "https://g.example/m/1", "status": "published"}\n```'
    with pytest.raises(PublisherCompletionError):
        parse_publisher_completion(text)


def test_repo_path_from_mr_url_extracts_namespace_path():
    from lc_server.integrations.gitlab_mr_verification import repo_path_from_mr_url

    url = "https://gitlab.example.com/group/sub/project/-/merge_requests/42"
    assert repo_path_from_mr_url(url) == "group/sub/project"


def test_repo_path_from_mr_url_rejects_non_mr_url():
    from lc_server.integrations.gitlab_mr_verification import repo_path_from_mr_url

    with pytest.raises(ValueError, match="not a GitLab MR url"):
        repo_path_from_mr_url("https://gitlab.example.com/group/project/-/issues/1")


class _FakePublisherAgent:
    def __init__(self, final_response: str):
        self._final_response = final_response
        self.prompts: list[str] = []
        self.gitlab_write_violations: list = []

    def run_conversation(self, prompt: str, task_id: str | None = None) -> dict:
        from delivery_runtime.shadow.guards import check_mcp_tool

        self.prompts.append(prompt)
        # Simulate the GitLab MCP write the real publisher performs; the
        # role contextvar set by execute() must allow it in standard mode.
        violation = check_mcp_tool("gitlab", "create_merge_request")
        if violation is not None:
            self.gitlab_write_violations.append(violation)
        return {"final_response": self._final_response, "completed": True}


@pytest.fixture
def _git_identity(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@example.com")


def _git(workspace, *args: str) -> str:
    import subprocess

    result = subprocess.run(
        ["git", *args],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _make_delivery_workspace(tmp_path, branch: str):
    """Tmp git repo on the delivery branch with uncommitted developer work."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    (workspace / "README.md").write_text("base\n", encoding="utf-8")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "-m", "baseline")
    _git(workspace, "checkout", "-b", branch)
    (workspace / "fix.txt").write_text("approved fix\n", encoding="utf-8")
    _git(workspace, "add", "fix.txt")
    return workspace


def test_publisher_execute_publishes_and_records_draft(_isolate_hermes_home, _git_identity, tmp_path, monkeypatch):
    from delivery_runtime.development import scope_enforcement
    from delivery_runtime.mr_drafts.models import MergeRequestDraft
    from delivery_runtime.mr_drafts.store import load_mr_draft, save_mr_draft
    from delivery_runtime.persistence.db import connect, init_db, utc_now_iso
    from lc_server.agent_bridge.hermes_publisher import HermesPublisherAgent

    init_db()
    now = utc_now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO work_orders (
                id, jira_key, title, description, priority, status, current_stage,
                confidence, created_at, updated_at
            ) VALUES ('WO-PUB-1', 'AAC-9', 'Demo', '', 'High', 'running', 'mr_publication', 0.8, ?, ?)
            """,
            (now, now),
        )
    draft = save_mr_draft(
        MergeRequestDraft(
            id="MRD-PUB-1",
            work_order_id="WO-PUB-1",
            title="AAC-9: fix callback",
            description="### Context\nfix",
            ticket_summary="",
            implementation_summary="",
            files_modified=[],
            risks=[],
            reviewers=[],
            qa_checklist={},
            decision_trace={},
            status="approved",
            created_at=now,
            updated_at=now,
        )
    )

    workspace = _make_delivery_workspace(tmp_path, "feature/AAC-9")
    baseline_head = _git(workspace, "rev-parse", "HEAD")

    guard_calls: list[dict] = []
    original_guard = scope_enforcement.guard_from_context

    def capture_guard(**kwargs):
        guard_calls.append(kwargs)
        return original_guard(**kwargs)

    monkeypatch.setattr(scope_enforcement, "guard_from_context", capture_guard)

    verified: list[tuple] = []
    monkeypatch.setattr(
        HermesPublisherAgent,
        "_verify_mr_exists",
        staticmethod(lambda project_key, completion: verified.append((project_key, completion))),
    )

    fake_agent = _FakePublisherAgent(
        "Pushed and created the MR.\n"
        '```json\n{"mrUrl": "https://gitlab.example.com/g/p/-/merge_requests/7", '
        '"mrIid": 7, "targetBranch": "develop", "status": "published"}\n```'
    )
    publisher = HermesPublisherAgent(agent_factory=lambda **kwargs: fake_agent)

    completion = publisher.execute(
        "WO-PUB-1",
        {
            "draftId": draft.id,
            "jiraKey": "AAC-9",
            "mrTitle": draft.title,
            "mrDescription": draft.description,
            "deliveryBranch": "feature/AAC-9",
            "integrationBranch": "develop",
            "workspacePath": str(workspace),
            "projectKey": "AAC",
        },
    )

    assert completion["mrIid"] == 7
    assert completion["status"] == "published"
    assert fake_agent.prompts and "feature/AAC-9" in fake_agent.prompts[0]

    # The pending developer work was committed on the delivery branch before
    # the publisher agent ran.
    assert _git(workspace, "rev-parse", "HEAD") != baseline_head
    assert _git(workspace, "status", "--porcelain") == ""
    assert "AAC-9" in _git(workspace, "log", "-1", "--format=%s")
    assert "fix.txt" in _git(workspace, "show", "--name-only", "--format=", "HEAD")
    assert fake_agent.gitlab_write_violations == []
    assert verified == [("AAC", completion)]

    assert guard_calls and guard_calls[0]["allow_git_push"] is True
    assert guard_calls[0]["task_id"] == "delivery-publish-WO-PUB-1"

    updated_draft = load_mr_draft(draft.id)
    assert updated_draft is not None
    assert updated_draft.mr_url == "https://gitlab.example.com/g/p/-/merge_requests/7"
    assert updated_draft.mr_iid == 7


def test_publisher_execute_requires_workspace(tmp_path):
    from lc_server.agent_bridge.hermes_publisher import HermesPublisherAgent

    publisher = HermesPublisherAgent(agent_factory=lambda **kwargs: None)
    with pytest.raises(PublisherCompletionError, match="workspace not found"):
        publisher.execute(
            "WO-PUB-2",
            {"workspacePath": str(tmp_path / "missing"), "projectKey": "AAC"},
        )


def test_publisher_execute_requires_delivery_branch(tmp_path):
    from lc_server.agent_bridge.hermes_publisher import HermesPublisherAgent

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    publisher = HermesPublisherAgent(agent_factory=lambda **kwargs: None)
    with pytest.raises(PublisherCompletionError, match="delivery branch"):
        publisher.execute(
            "WO-PUB-3",
            {"workspacePath": str(workspace), "projectKey": "AAC"},
        )


def test_publisher_execute_fails_on_wrong_branch(_git_identity, tmp_path):
    from lc_server.agent_bridge.hermes_publisher import HermesPublisherAgent

    workspace = _make_delivery_workspace(tmp_path, "feature/AAC-9")
    _git(workspace, "stash")
    _git(workspace, "checkout", "main")

    agent_ran: list[bool] = []
    publisher = HermesPublisherAgent(agent_factory=lambda **kwargs: agent_ran.append(True))
    with pytest.raises(RuntimeError, match="feature/AAC-9"):
        publisher.execute(
            "WO-PUB-4",
            {
                "workspacePath": str(workspace),
                "deliveryBranch": "feature/AAC-9",
                "jiraKey": "AAC-9",
                "projectKey": "AAC",
            },
        )
    assert agent_ran == []
