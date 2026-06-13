"""Role-aware GitLab write tool enforcement."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from delivery_runtime.shadow.context import current_delivery_agent_role, delivery_agent_role
from delivery_runtime.shadow.guards import check_mcp_tool


def test_standard_mode_blocks_gitlab_write_for_default_role(monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_SHADOW_MODE", raising=False)
    violation = check_mcp_tool("gitlab", "create_merge_request")
    assert violation is not None
    assert violation.category == "gitlab"
    assert "publisher" in violation.detail
    assert "none" in violation.detail


def test_standard_mode_allows_gitlab_write_for_publisher(monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_SHADOW_MODE", raising=False)
    with delivery_agent_role("publisher"):
        violation = check_mcp_tool("gitlab", "create_merge_request")
    assert violation is None


def test_standard_mode_blocks_gitlab_write_for_developer_role(monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_SHADOW_MODE", raising=False)
    with delivery_agent_role("developer"):
        violation = check_mcp_tool("gitlab", "create_merge_request")
    assert violation is not None
    assert "developer" in violation.detail


def test_standard_mode_allows_gitlab_reads_for_any_role(monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_SHADOW_MODE", raising=False)
    violation = check_mcp_tool("gitlab", "get_merge_request")
    assert violation is None


def test_standard_mode_leaves_non_gitlab_tools_untouched(monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_SHADOW_MODE", raising=False)
    assert check_mcp_tool("jira", "create_issue") is None
    assert check_mcp_tool("slack", "post_message") is None


def test_shadow_mode_blocks_generic_post_message_tool(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_SHADOW_MODE", "1")

    violation = check_mcp_tool("slack", "post_message")

    assert violation is not None
    assert violation.category == "mcp"
    assert violation.operation == "post_message"


def test_shadow_mode_blocks_gitlab_write_even_for_publisher(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_SHADOW_MODE", "true")
    with delivery_agent_role("publisher"):
        violation = check_mcp_tool("gitlab", "create_merge_request")
    assert violation is not None
    assert violation.category == "gitlab"
    assert "shadow mode" in violation.detail


def test_create_branch_allowed_for_publisher(monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_SHADOW_MODE", raising=False)
    with delivery_agent_role("publisher"):
        violation = check_mcp_tool("gitlab", "create_branch")
    assert violation is None


def test_role_context_resets_after_exit(monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_SHADOW_MODE", raising=False)
    with delivery_agent_role("publisher"):
        assert current_delivery_agent_role() == "publisher"
    assert current_delivery_agent_role() == ""
    assert check_mcp_tool("gitlab", "create_merge_request") is not None


# ── Dispatch-level enforcement (real agent path) ────────────────────────────
#
# Agents call MCP tools through the registry handler built by
# tools.mcp_tool._make_tool_handler — NOT through invoke_mcp_tool. These
# tests go through that real handler with a stub MCP server installed to
# prove the shadow/role guard is enforced on the dispatch path.


@pytest.fixture
def _stub_gitlab_server():
    pytest.importorskip("mcp")
    from tools import mcp_tool

    call_count = {"n": 0}

    async def _call_tool_success(*args, **kwargs):
        call_count["n"] += 1
        result = MagicMock()
        result.isError = False
        block = MagicMock()
        block.text = "ok"
        result.content = [block]
        result.structuredContent = None
        return result

    server = MagicMock()
    server.name = "gitlab"
    session = MagicMock()
    session.call_tool = _call_tool_success
    server.session = session
    server._ready = MagicMock()
    server._ready.is_set.return_value = True

    mcp_tool._servers["gitlab"] = server
    mcp_tool._server_error_counts.pop("gitlab", None)
    mcp_tool._ensure_mcp_loop()
    try:
        yield mcp_tool, call_count
    finally:
        mcp_tool._servers.pop("gitlab", None)
        mcp_tool._server_error_counts.pop("gitlab", None)


def test_dispatch_blocks_gitlab_write_for_default_role(monkeypatch, _stub_gitlab_server):
    monkeypatch.delenv("LIVINGCOLOR_SHADOW_MODE", raising=False)
    mcp_tool, call_count = _stub_gitlab_server

    handler = mcp_tool._make_tool_handler("gitlab", "create_merge_request", 10.0)
    parsed = json.loads(handler({}))

    assert parsed.get("blocked") is True
    assert "publisher" in parsed.get("error", "")
    assert call_count["n"] == 0, "blocked call must never reach the MCP session"


def test_dispatch_allows_gitlab_write_for_publisher(monkeypatch, _stub_gitlab_server):
    monkeypatch.delenv("LIVINGCOLOR_SHADOW_MODE", raising=False)
    mcp_tool, call_count = _stub_gitlab_server

    handler = mcp_tool._make_tool_handler("gitlab", "create_merge_request", 10.0)
    with delivery_agent_role("publisher"):
        parsed = json.loads(handler({}))

    assert parsed.get("result") == "ok", parsed
    assert call_count["n"] == 1


def test_dispatch_blocks_gitlab_write_in_shadow_mode_even_for_publisher(
    monkeypatch, _stub_gitlab_server
):
    monkeypatch.setenv("LIVINGCOLOR_SHADOW_MODE", "true")
    mcp_tool, call_count = _stub_gitlab_server

    handler = mcp_tool._make_tool_handler("gitlab", "create_merge_request", 10.0)
    with delivery_agent_role("publisher"):
        parsed = json.loads(handler({}))

    assert parsed.get("blocked") is True
    assert parsed.get("shadowMode") is True
    assert call_count["n"] == 0


# ── GitHub write tool enforcement ─────────────────────────────────────────────


def test_github_create_pull_request_blocked_without_publisher_role(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_SHADOW_MODE", "1")

    violation = check_mcp_tool("github", "create_pull_request")

    assert violation is not None
    assert violation.category == "github"
    assert violation.operation == "createpullrequest"


def test_github_create_pull_request_allowed_for_publisher(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_SHADOW_MODE", "1")

    with delivery_agent_role("publisher"):
        assert check_mcp_tool("github", "create_pull_request") is None


def test_standard_mode_blocks_github_write_for_default_role(monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_SHADOW_MODE", raising=False)
    violation = check_mcp_tool("github", "create_pull_request")
    assert violation is not None
    assert violation.category == "github"
    assert "publisher" in violation.detail
    assert "none" in violation.detail


def test_standard_mode_allows_github_write_for_publisher(monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_SHADOW_MODE", raising=False)
    with delivery_agent_role("publisher"):
        violation = check_mcp_tool("github", "create_pull_request")
    assert violation is None


def test_standard_mode_blocks_github_write_for_developer_role(monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_SHADOW_MODE", raising=False)
    with delivery_agent_role("developer"):
        violation = check_mcp_tool("github", "create_pull_request")
    assert violation is not None
    assert "developer" in violation.detail


def test_standard_mode_allows_github_reads_for_any_role(monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_SHADOW_MODE", raising=False)
    violation = check_mcp_tool("github", "get_pull_request")
    assert violation is None
