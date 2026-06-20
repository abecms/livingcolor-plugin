from __future__ import annotations

import os
from unittest.mock import patch

import yaml


def test_jira_mcp_config_requires_url_and_token(monkeypatch):
    from lc_server.integrations.mcp_env_bootstrap import _jira_mcp_config_from_env

    monkeypatch.delenv("JIRA_URL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    assert _jira_mcp_config_from_env() is None

    monkeypatch.setenv("JIRA_URL", "https://livingcolor.atlassian.net")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")
    monkeypatch.setenv("JIRA_USERNAME", "user@example.com")

    cfg = _jira_mcp_config_from_env()
    assert cfg is not None
    assert cfg["command"] == "uvx"
    assert cfg["env"]["JIRA_URL"] == "https://livingcolor.atlassian.net"
    assert cfg["env"]["JIRA_API_TOKEN"] == "token"
    assert cfg["env"]["JIRA_USERNAME"] == "user@example.com"


def test_github_mcp_config_accepts_gh_token_alias(monkeypatch):
    from lc_server.integrations.mcp_env_bootstrap import _github_mcp_config_from_env

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GH_TOKEN", "ghp_test")

    cfg = _github_mcp_config_from_env()
    assert cfg is not None
    assert cfg["env"]["GITHUB_TOKEN"] == "ghp_test"
    assert cfg["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"] == "ghp_test"


def test_ensure_mcp_servers_from_env_writes_config_yaml(tmp_path, monkeypatch):
    from lc_server.integrations import mcp_env_bootstrap as module

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()

    monkeypatch.setenv("JIRA_URL", "https://livingcolor.atlassian.net")
    monkeypatch.setenv("JIRA_API_TOKEN", "jira-token")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")

    with patch(
        "lc_server.integrations.mcp_config_bridge.default_hermes_root",
        return_value=hermes_home,
    ), patch(
        "lc_server.integrations.mcp_env_bootstrap._save_via_hermes",
        return_value=False,
    ):
        provisioned = module.ensure_mcp_servers_from_env()

    assert set(provisioned) == {"jira", "github"}
    cfg_path = hermes_home / "config.yaml"
    assert cfg_path.is_file()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert data["mcp_servers"]["jira"]["env"]["JIRA_API_TOKEN"] == "jira-token"
    assert data["mcp_servers"]["github"]["env"]["GITHUB_TOKEN"] == "ghp_test"


def test_credential_env_status_never_returns_values(monkeypatch):
    from lc_server.integrations.mcp_env_bootstrap import credential_env_status

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_super_secret_value")
    status = credential_env_status()
    assert status["GITHUB_TOKEN"] == "configured"
    assert "ghp_" not in str(status.values())


def test_prerequisites_auto_provisions_mcp_from_env(monkeypatch, tmp_path):
    from lc_server.provisioning.prerequisites import check_provisioning_prerequisites

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()

    monkeypatch.setenv("JIRA_URL", "https://livingcolor.atlassian.net")
    monkeypatch.setenv("JIRA_API_TOKEN", "jira-token")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("LIVINGCOLOR_ANALYST_BACKEND", "heuristic")
    monkeypatch.setenv("LIVINGCOLOR_PLANNER_BACKEND", "heuristic")
    monkeypatch.setenv("LIVINGCOLOR_DEVELOPER_BACKEND", "heuristic")
    monkeypatch.setenv("LIVINGCOLOR_PUBLISHER_BACKEND", "heuristic")

    with patch(
        "lc_server.integrations.mcp_config_bridge.default_hermes_root",
        return_value=hermes_home,
    ), patch(
        "lc_server.integrations.mcp_env_bootstrap._save_via_hermes",
        return_value=False,
    ), patch(
        "lc_server.provisioning.prerequisites.load_project_vcs_provider",
        return_value="github",
    ), patch(
        "lc_server.provisioning.prerequisites.is_delivery_llm_available",
        return_value=False,
    ):
        missing = check_provisioning_prerequisites("TVP")

    assert missing == []
    cfg = yaml.safe_load((hermes_home / "config.yaml").read_text(encoding="utf-8"))
    assert "jira" in cfg["mcp_servers"]
    assert "github" in cfg["mcp_servers"]
