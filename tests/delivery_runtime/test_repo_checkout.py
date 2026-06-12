"""Managed repository checkout tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from delivery_runtime.context.repo_checkout import (
    ensure_managed_checkout,
    fetch_managed_checkout,
    managed_checkout_path,
)


def test_managed_checkout_path_uses_livingcolor_project_directory(_isolate_hermes_home):
    path = managed_checkout_path("TVP", "tv5monde/tv5mondeplus-front")
    assert path.name == "tv5mondeplus-front"
    assert path.parent.name == "tv5monde"
    assert path.parent.parent.name == "TVP"


def test_ensure_managed_checkout_clones_when_missing(_isolate_hermes_home, tmp_path: Path):
    target = managed_checkout_path("TVP", "tv5monde/demo-repo")

    def fake_clone(url: str, destination: Path) -> bool:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / ".git").mkdir()
        return True

    project_cfg = {
        "integrations": {
            "mcp_servers": {
                "gitlab": {
                    "env": {
                        "GITLAB_API_URL": "https://gitlab.example.com/api/v4",
                        "GITLAB_PERSONAL_ACCESS_TOKEN": "test-token",
                    }
                }
            }
        }
    }

    with patch("delivery_runtime.context.repo_checkout.managed_checkout_path", return_value=target), patch(
        "delivery_runtime.context.repo_checkout._clone_repository", side_effect=fake_clone
    ) as clone_mock:
        result = ensure_managed_checkout(project_key="TVP", repo_id="tv5monde/demo-repo", project_cfg=project_cfg)

    assert result == str(target)
    clone_mock.assert_called_once()
    assert "oauth2:test-token@gitlab.example.com/tv5monde/demo-repo.git" in clone_mock.call_args.args[0]


def test_ensure_managed_checkout_returns_existing_path(_isolate_hermes_home, tmp_path: Path):
    target = tmp_path / "TVP" / "tv5monde" / "demo-repo"
    target.mkdir(parents=True)
    (target / ".git").mkdir()

    with patch("delivery_runtime.context.repo_checkout.managed_checkout_path", return_value=target), patch(
        "delivery_runtime.context.repo_checkout._refresh_checkout", return_value=True
    ) as refresh_mock:
        result = ensure_managed_checkout(
            project_key="TVP",
            repo_id="tv5monde/demo-repo",
            project_cfg={"integrations": {}},
        )

    assert result == str(target)
    refresh_mock.assert_called_once_with(target)


def test_ensure_managed_checkout_without_gitlab_token_returns_none(_isolate_hermes_home):
    result = ensure_managed_checkout(
        project_key="TVP",
        repo_id="tv5monde/demo-repo",
        project_cfg={"integrations": {}},
    )
    assert result is None


def test_fetch_managed_checkout_fetches_without_reset(_isolate_hermes_home, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    hermes_home = _isolate_hermes_home
    livingcolor_home = hermes_home / "livingcolor"
    livingcolor_home.mkdir(parents=True)
    target = livingcolor_home / "TVP" / "tv5monde" / "demo-repo"
    target.mkdir(parents=True)
    (target / ".git").mkdir()

    with patch("delivery_runtime.context.repo_checkout.subprocess.run") as run_mock:
        run_mock.return_value.returncode = 0
        assert fetch_managed_checkout(target) is True

    run_mock.assert_called_once()
    assert run_mock.call_args.args[0] == ["git", "fetch", "--depth", "1", "origin"]
    assert run_mock.call_args.kwargs["cwd"] == target
