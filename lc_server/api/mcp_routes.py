"""LivingColor MCP routes for integration upsert, connect, status, and test."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from lc_server.integrations.mcp_connect import (
    connect_github_mcp,
    connect_gitlab_mcp,
    connect_mcp_server,
    integration_status,
    resolve_integration_server_entry,
    status_mcp_server,
    upsert_integration_server_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp"])


@router.put("/servers/{name}")
async def upsert_mcp_server(name: str, body: dict[str, Any]):
    try:
        return await asyncio.to_thread(upsert_integration_server_config, name, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("PUT /mcp/servers/%s failed", name)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/servers/{name}/connect")
async def connect_mcp_server_route(name: str):
    safe_name = (name or "").strip().lower()
    if safe_name == "gitlab":
        try:
            return await asyncio.to_thread(connect_gitlab_mcp)
        except Exception as exc:
            logger.exception("POST /mcp/servers/gitlab/connect failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    if safe_name == "github":
        try:
            return await asyncio.to_thread(connect_github_mcp)
        except Exception as exc:
            logger.exception("POST /mcp/servers/github/connect failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    entry = await asyncio.to_thread(resolve_integration_server_entry, name)
    if not entry:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' is not configured")

    resolved_name, cfg = entry
    try:
        return await asyncio.to_thread(connect_mcp_server, resolved_name, cfg)
    except Exception as exc:
        logger.exception("POST /mcp/servers/%s/connect failed", resolved_name)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/servers/{name}/status")
async def get_mcp_server_status(name: str):
    safe_name = (name or "").strip().lower()
    if safe_name in {"jira", "gitlab", "github"}:
        try:
            return await asyncio.to_thread(integration_status, safe_name)
        except Exception as exc:
            logger.exception("GET /mcp/servers/%s/status failed", safe_name)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    entry = await asyncio.to_thread(resolve_integration_server_entry, name)
    if not entry:
        return {
            "ok": False,
            "status": "disconnected",
            "message": f"MCP server '{name}' is not configured yet.",
            "authenticated": False,
            "toolCount": 0,
            "configured": False,
        }

    resolved_name, cfg = entry
    try:
        payload = await asyncio.to_thread(status_mcp_server, resolved_name, cfg)
        payload["configured"] = True
        return payload
    except Exception as exc:
        logger.exception("GET /mcp/servers/%s/status failed", resolved_name)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/integrations/status")
async def get_integrations_status():
    try:
        jira, gitlab, github = await asyncio.gather(
            asyncio.to_thread(integration_status, "jira"),
            asyncio.to_thread(integration_status, "gitlab"),
            asyncio.to_thread(integration_status, "github"),
        )
    except Exception as exc:
        logger.exception("GET /mcp/integrations/status failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"jira": jira, "gitlab": gitlab, "github": github}


@router.post("/servers/{name}/test")
async def test_mcp_server_route(name: str):
    from hermes_cli.mcp_config import _probe_single_server

    entry = await asyncio.to_thread(resolve_integration_server_entry, name)
    if not entry:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' is not configured")

    resolved_name, cfg = entry
    try:
        result = await asyncio.to_thread(_probe_single_server, resolved_name, dict(cfg))
    except Exception as exc:
        logger.exception("POST /mcp/servers/%s/test failed", resolved_name)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    ok = bool(result.get("ok"))
    return {
        "ok": ok,
        "error": None if ok else str(result.get("error") or "MCP server test failed"),
        "tools": result.get("tools") or [],
    }
