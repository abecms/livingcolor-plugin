from __future__ import annotations

from unittest.mock import patch


def test_discover_github_repos_prefers_project_key_match():
    from lc_server.integrations.vcs.github import discover_github_repos

    repos = [
        {"full_name": "org/gh-service", "name": "gh-service", "updated_at": "2026-06-10T00:00:00Z"},
        {"full_name": "org/other", "name": "other", "updated_at": "2026-06-11T00:00:00Z"},
    ]

    result = discover_github_repos("GH", repos)

    assert result.default_repo == "github.com/org/gh-service"
    assert result.repos == [{"path": "github.com/org/gh-service", "githubId": None}]
    assert result.warnings == []


def test_discover_github_repos_for_project_uses_fetch():
    from lc_server.integrations.vcs.github import discover_github_repos_for_project

    mcp_config = {"env": {"GITHUB_TOKEN": "ghp_test"}}
    fetched = [{"id": 1, "full_name": "org/app", "name": "app", "updated_at": "2026-06-11T00:00:00Z"}]

    with patch("lc_server.integrations.vcs.github._fetch_github_repositories", return_value=fetched) as mock_fetch:
        result = discover_github_repos_for_project("APP", mcp_config)

    mock_fetch.assert_called_once_with(mcp_config)
    assert result.default_repo == "github.com/org/app"
    assert result.repos[0]["githubId"] == 1
