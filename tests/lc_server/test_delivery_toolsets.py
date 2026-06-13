"""Delivery agent toolset resolution."""

from __future__ import annotations


def test_resolve_publisher_toolsets_uses_github_server(monkeypatch):
    from lc_server.agent_bridge.delivery_toolsets import resolve_publisher_toolsets

    monkeypatch.setattr(
        "lc_server.agent_bridge.delivery_toolsets._project_mcp_server_names",
        lambda project_key: ["github"],
    )
    monkeypatch.setattr(
        "lc_server.agent_bridge.delivery_toolsets._configured_mcp_server_names",
        lambda: [],
    )
    monkeypatch.setattr(
        "lc_server.agent_bridge.delivery_toolsets.load_project_vcs_provider",
        lambda project_key: "github",
    )

    assert "mcp-github" in resolve_publisher_toolsets(
        base_toolsets=["terminal", "skills"],
        manifest=None,
        project_key="GH",
    )


def test_resolve_publisher_toolsets_defaults_to_gitlab(monkeypatch):
    from lc_server.agent_bridge.delivery_toolsets import resolve_publisher_toolsets

    monkeypatch.setattr(
        "lc_server.agent_bridge.delivery_toolsets._project_mcp_server_names",
        lambda project_key: ["gitlab"],
    )
    monkeypatch.setattr(
        "lc_server.agent_bridge.delivery_toolsets._configured_mcp_server_names",
        lambda: [],
    )
    monkeypatch.setattr(
        "lc_server.agent_bridge.delivery_toolsets.load_project_vcs_provider",
        lambda project_key: "gitlab",
    )

    assert "mcp-gitlab" in resolve_publisher_toolsets(
        base_toolsets=["terminal", "skills"],
        manifest=None,
        project_key="TVP",
    )
