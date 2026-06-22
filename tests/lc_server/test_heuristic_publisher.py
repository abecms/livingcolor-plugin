"""Tests for heuristic GitHub publication helpers."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from lc_server.agent_bridge.heuristic_publisher import (
    create_github_pull_request,
    find_existing_github_pull_request,
)


def test_find_existing_github_pull_request_parses_open_pr():
    payload = [{"number": 5, "html_url": "https://github.com/org/repo/pull/5"}]
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = find_existing_github_pull_request(
            token="token",
            repo_path="github.com/org/repo",
            head_branch="feature/TVP-10",
            base_branch="preprod",
        )
    assert result == payload[0]


def test_create_github_pull_request_reuses_existing_on_422():
    existing = {"number": 5, "html_url": "https://github.com/org/repo/pull/5"}
    http_error = __import__("urllib.error").error.HTTPError(
        url="https://api.github.com/repos/org/repo/pulls",
        code=422,
        msg="Unprocessable Entity",
        hdrs=None,
        fp=MagicMock(read=MagicMock(return_value=b'{"message":"already exists"}')),
    )

    with patch(
        "lc_server.agent_bridge.heuristic_publisher.find_existing_github_pull_request",
        return_value=existing,
    ):
        with patch("urllib.request.urlopen", side_effect=http_error):
            result = create_github_pull_request(
                token="token",
                repo_path="github.com/org/repo",
                title="t",
                body="b",
                head_branch="feature/TVP-10",
                base_branch="preprod",
            )
    assert result == existing
