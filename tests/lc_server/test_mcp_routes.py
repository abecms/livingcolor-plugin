"""Tests for LivingColor MCP plugin routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lc_server.api.mcp_routes import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/mcp")
    return TestClient(app)


def test_upsert_mcp_server_route_saves_config(client):
    saved: dict[str, object] = {}

    def fake_save(name: str, config: dict) -> bool:
        saved["name"] = name
        saved["config"] = config
        return True

    with patch("hermes_cli.mcp_config._get_mcp_servers", return_value={}), patch(
        "hermes_cli.mcp_config._save_mcp_server", side_effect=fake_save
    ):
        response = client.put(
            "/mcp/servers/jira",
            json={
                "command": "uvx",
                "args": ["mcp-atlassian"],
                "env": {
                    "JIRA_URL": "https://example.atlassian.net/",
                    "JIRA_USERNAME": "user@example.com",
                    "JIRA_API_TOKEN": "secret",
                },
            },
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "name": "jira"}
    assert saved["name"] == "jira"


def test_upsert_mcp_server_route_updates_existing_alias(client):
    saved: dict[str, object] = {}
    existing = {
        "Atlassian": {
            "command": "uvx",
            "args": ["mcp-atlassian"],
            "env": {"JIRA_URL": "https://example.atlassian.net/"},
        }
    }

    def fake_save(name: str, config: dict) -> bool:
        saved["name"] = name
        saved["config"] = config
        return True

    with patch("hermes_cli.mcp_config._get_mcp_servers", return_value=existing), patch(
        "hermes_cli.mcp_config._save_mcp_server", side_effect=fake_save
    ):
        response = client.put(
            "/mcp/servers/jira",
            json={
                "command": "uvx",
                "args": ["mcp-atlassian"],
                "env": {
                    "JIRA_URL": "https://example.atlassian.net/",
                    "JIRA_USERNAME": "user@example.com",
                    "JIRA_API_TOKEN": "secret",
                },
            },
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "name": "Atlassian"}
    assert saved["name"] == "Atlassian"


def test_connect_mcp_server_route_returns_connected_payload(client):
    with patch(
        "lc_server.api.mcp_routes.connect_gitlab_mcp",
        return_value={
            "ok": True,
            "status": "connected",
            "message": "Connected via MCP.",
            "authenticated": True,
            "toolCount": 1,
            "gitlabUrl": "https://gitlab.com",
            "serverName": "gitlab-tv5",
        },
    ):
        response = client.post("/mcp/servers/gitlab/connect")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["status"] == "connected"
    assert body["toolCount"] == 1
    assert body["gitlabUrl"] == "https://gitlab.com"


def test_get_mcp_server_status_route_reports_missing_server(client):
    with patch("hermes_cli.mcp_config._get_mcp_servers", return_value={}):
        response = client.get("/mcp/servers/jira/status")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["authenticated"] is False
