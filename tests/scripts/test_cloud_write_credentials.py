"""Tests for cloud credential provisioning scripts."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_parse_and_merge_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import cloud_write_credentials as module

    env_path = tmp_path / "livingcolor" / ".env"
    monkeypatch.setattr(module, "_livingcolor_env_path", lambda: env_path)

    values = module.parse_lines(
        [
            "JIRA_URL=https://livingcolor.atlassian.net",
            "JIRA_API_TOKEN=secret-token",
            "# comment",
            "",
            "GITHUB_TOKEN=ghp_test",
        ]
    )
    written = module.merge_env_file(env_path, values)

    assert written == ["GITHUB_TOKEN", "JIRA_API_TOKEN", "JIRA_URL"]
    assert env_path.read_text(encoding="utf-8").count("=") == 3
    assert (env_path.stat().st_mode & 0o777) == 0o600

    module.merge_env_file(env_path, {"STRIPE_SECRET_KEY": "sk_test_x"})
    merged = module.parse_lines(env_path.read_text(encoding="utf-8").splitlines())
    assert set(merged) == {"JIRA_URL", "JIRA_API_TOKEN", "GITHUB_TOKEN", "STRIPE_SECRET_KEY"}


def test_rejects_unknown_keys() -> None:
    from scripts import cloud_write_credentials as module

    with pytest.raises(ValueError, match="unsupported credential key"):
        module.parse_lines(["NOT_A_REAL_KEY=value"])


def test_export_sets_github_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import cloud_write_credentials as module

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    module.export_to_environ({"GH_TOKEN": "ghp_alias"})
    assert os.environ.get("GITHUB_TOKEN") == "ghp_alias"
