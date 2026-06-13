from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest


def test_repo_path_and_number_from_github_pr_url():
    from lc_server.integrations.vcs.github import repo_path_and_number_from_pr_url

    assert repo_path_and_number_from_pr_url("https://github.com/org/app/pull/42") == ("org/app", 42)


def test_repo_path_and_number_rejects_non_pr_url():
    from lc_server.integrations.vcs.github import repo_path_and_number_from_pr_url

    with pytest.raises(ValueError, match="not a GitHub PR url"):
        repo_path_and_number_from_pr_url("https://github.com/org/app/issues/42")


def test_verify_pull_request_exists_returns_payload(monkeypatch):
    from lc_server.integrations.vcs.github import verify_pull_request_exists

    payload = {"number": 42, "html_url": "https://github.com/org/app/pull/42"}
    response = io.BytesIO(json.dumps(payload).encode("utf-8"))

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return response.getvalue()

    mcp_config = {"env": {"GITHUB_TOKEN": "ghp_test"}}

    with patch("urllib.request.urlopen", return_value=_FakeResponse()) as mock_urlopen:
        found = verify_pull_request_exists(mcp_config=mcp_config, repo_path="org/app", pr_number=42)

    assert found == payload
    mock_urlopen.assert_called_once()
    request = mock_urlopen.call_args[0][0]
    assert request.full_url == "https://api.github.com/repos/org/app/pulls/42"
    assert request.get_header("Authorization") == "Bearer ghp_test"


def test_verify_pull_request_exists_returns_none_on_404(monkeypatch):
    import urllib.error

    from lc_server.integrations.vcs.github import verify_pull_request_exists

    mcp_config = {"env": {"GITHUB_TOKEN": "ghp_test"}}

    def _raise_404(*args, **kwargs):
        raise urllib.error.HTTPError(
            url="https://api.github.com/repos/org/app/pulls/99",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=io.BytesIO(b'{"message":"Not Found"}'),
        )

    with patch("urllib.request.urlopen", side_effect=_raise_404):
        found = verify_pull_request_exists(mcp_config=mcp_config, repo_path="org/app", pr_number=99)

    assert found is None
