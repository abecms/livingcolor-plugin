"""Shared fixtures for lc_server tests."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest


def _unconfigured(module: str, name: str):
    def _stub(*_args, **_kwargs):
        raise RuntimeError(f"{module}.{name} not patched in test")

    return _stub


class _JiraDashboardStub(ModuleType):
    """Lazy stub for agent-lc's hermes_cli.jira_dashboard (absent from upstream)."""

    JIRA_MCP_NAME = "jira"
    JiraDashboardError = RuntimeError

    @staticmethod
    def _issue_field(issue: dict, *paths: str) -> str:
        fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else issue
        for path in paths:
            value = fields.get(path) if isinstance(fields, dict) else issue.get(path)
            if isinstance(value, dict):
                for nested in ("displayName", "display_name", "name", "value", "key"):
                    inner = value.get(nested)
                    if isinstance(inner, str) and inner.strip():
                        return inner.strip()
            elif isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _issue_text_field(issue: dict, path: str) -> str:
        fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else issue
        value = fields.get(path) if isinstance(fields, dict) else issue.get(path)
        if isinstance(value, str):
            return " ".join(value.split())

        parts: list[str] = []

        def walk(node):
            if isinstance(node, dict):
                text = node.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
                for child in node.values():
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(value)
        return " ".join(" ".join(parts).split())

    def __getattr__(self, name: str):
        stub = _unconfigured("hermes_cli.jira_dashboard", name)
        setattr(self, name, stub)
        return stub


# Upstream hermes-agent has no jira_dashboard; stub it so lazy imports resolve.
if "hermes_cli.jira_dashboard" not in sys.modules:
    _jira_dashboard = _JiraDashboardStub("hermes_cli.jira_dashboard")
    sys.modules["hermes_cli.jira_dashboard"] = _jira_dashboard

    import hermes_cli

    hermes_cli.jira_dashboard = _jira_dashboard  # noqa: SLF001 — test stub

# agent-lc adds hermes_cli.mcp_runtime for saved MCP session restore.
if "hermes_cli.mcp_runtime" not in sys.modules:
    _mcp_runtime = ModuleType("hermes_cli.mcp_runtime")
    _mcp_runtime.connect_mcp_server = _unconfigured("hermes_cli.mcp_runtime", "connect_mcp_server")
    sys.modules["hermes_cli.mcp_runtime"] = _mcp_runtime

    import hermes_cli

    hermes_cli.mcp_runtime = _mcp_runtime  # noqa: SLF001 — test stub

# agent-lc extends tools.mcp_tool with direct invoke helpers; stub for plugin tests.
import tools.mcp_tool

for _mcp_symbol in ("list_connected_mcp_raw_tool_names", "invoke_mcp_tool"):
    if not hasattr(tools.mcp_tool, _mcp_symbol):
        setattr(
            tools.mcp_tool,
            _mcp_symbol,
            _unconfigured("tools.mcp_tool", _mcp_symbol),
        )


@pytest.fixture
def livingcolor_home(tmp_path, monkeypatch):
    """Plugin data home at HERMES_HOME/livingcolor (see lc_constants)."""
    hermes_home = tmp_path / "hermes"
    lc_home = hermes_home / "livingcolor"
    lc_home.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    return lc_home
