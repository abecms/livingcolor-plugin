"""Tests for per-project MCP save hooks."""

from __future__ import annotations

from unittest.mock import patch

import hermes_cli.mcp_config as mcp_config
import pytest

from lc_server.context import ProjectContext, reset_project_context, set_project_context
from lc_server.integrations.project_mcp_runtime import install_project_mcp_hooks


def _reset_hook(monkeypatch, save_impl):
    setattr(mcp_config, "_livingcolor_project_mcp_hook_installed", False)
    monkeypatch.setattr(mcp_config, "_save_mcp_server", save_impl)
    install_project_mcp_hooks()


def test_project_mcp_hook_returns_true_when_original_save_succeeds(monkeypatch):
    _reset_hook(monkeypatch, lambda name, server_config: True)

    token = set_project_context(ProjectContext(org_id="local", project_key="BIBNUM"))
    try:
        with patch("lc_server.integrations.project_mcp_runtime.persist_project_mcp_server") as persist:
            result = mcp_config._save_mcp_server(
                "gitlab",
                {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-gitlab"],
                },
            )
    finally:
        reset_project_context(token)

    assert result is True
    persist.assert_called_once()


def test_project_mcp_hook_returns_false_when_original_save_fails(monkeypatch):
    _reset_hook(monkeypatch, lambda name, server_config: False)

    token = set_project_context(ProjectContext(org_id="local", project_key="BIBNUM"))
    try:
        with patch("lc_server.integrations.project_mcp_runtime.persist_project_mcp_server"):
            result = mcp_config._save_mcp_server("gitlab", {"command": "npx", "args": []})
    finally:
        reset_project_context(token)

    assert result is False
