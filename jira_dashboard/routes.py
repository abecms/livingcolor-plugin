"""Jira PM dashboard HTTP routes for the LivingColor Hermes plugin."""

from __future__ import annotations

import asyncio
import base64
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jira"])


@router.get("/dashboard")
async def get_jira_dashboard(reconnect: bool = False, project: str | None = None):
    """Return project dashboard data sourced from the Jira MCP server."""
    from jira_dashboard.service import fetch_jira_dashboard

    try:
        payload = await asyncio.to_thread(
            fetch_jira_dashboard,
            reconnect=reconnect,
            project_key=project,
        )
        sprint_metric = next(
            (metric for metric in payload.get("metrics", []) if metric.get("label") == "Sprint health"),
            None,
        )
        if sprint_metric:
            payload["sprintHealth"] = sprint_metric
    except Exception as exc:
        logger.exception("GET /dashboard failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return payload


@router.post("/sync")
async def post_jira_sync(body: Dict[str, Any] | None = None):
    raise HTTPException(status_code=410, detail="Jira intelligence sync was removed from LivingColor.")


@router.get("/sync/status")
async def get_jira_sync_status(project: str = ""):
    return {
        "cursor": None,
        "message": "Jira intelligence sync disabled.",
        "projectKey": project or None,
        "status": "idle",
    }


@router.get("/intelligence/context")
async def get_jira_intelligence_context(project: str, intent: str = "triage", issues: str = ""):
    raise HTTPException(status_code=410, detail="Jira intelligence was removed from LivingColor.")


@router.post("/intelligence/signals/{signal_id}/validation")
async def post_jira_signal_validation(signal_id: int, body: Dict[str, Any] | None = None):
    raise HTTPException(status_code=410, detail="Jira intelligence was removed from LivingColor.")


@router.get("/intelligence/signals/quality")
async def get_jira_signal_quality(project: str):
    raise HTTPException(status_code=410, detail="Jira intelligence was removed from LivingColor.")


@router.get("/intelligence/signals/candidates")
async def get_jira_signal_candidates(project: str):
    raise HTTPException(status_code=410, detail="Jira intelligence was removed from LivingColor.")


@router.post("/intelligence/risk-review")
async def post_jira_intelligence_risk_review(body: Dict[str, Any] | None = None):
    raise HTTPException(status_code=410, detail="Jira intelligence was removed from LivingColor.")


@router.post("/intelligence/report")
async def post_jira_intelligence_report(body: Dict[str, Any] | None = None):
    raise HTTPException(status_code=410, detail="Jira intelligence was removed from LivingColor.")


@router.get("/issues/{issue_key}/attachments")
async def get_jira_issue_attachments(issue_key: str):
    """Return attachments for one Jira issue on demand."""
    from jira_dashboard.service import fetch_jira_issue_attachments

    try:
        attachments = await asyncio.to_thread(fetch_jira_issue_attachments, issue_key)
    except Exception as exc:
        logger.exception("GET /issues/%s/attachments failed", issue_key)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"attachments": attachments}


@router.get("/attachments/preview")
async def preview_jira_attachment(
    url: str = "",
    issue_key: str = "",
    attachment_id: str = "",
    name: str = "",
):
    """Proxy a Jira attachment through the desktop backend for in-app previews."""
    try:
        if issue_key:
            from jira_dashboard.service import fetch_jira_attachment_preview

            content, media_type = await asyncio.to_thread(
                fetch_jira_attachment_preview,
                issue_key,
                attachment_id=attachment_id,
                name=name,
            )
        else:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise HTTPException(status_code=400, detail="Invalid attachment URL.")
            content, media_type = await asyncio.to_thread(_download_jira_attachment_preview, url)
    except urllib.error.HTTPError as exc:
        logger.warning("GET /attachments/preview failed with HTTP %s", exc.code)
        raise HTTPException(status_code=exc.code, detail="Could not load Jira attachment preview.") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("GET /attachments/preview failed")
        raise HTTPException(status_code=502, detail="Could not load Jira attachment preview.") from exc

    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@router.get("/attachments/preview-data")
async def get_jira_attachment_preview_data(
    url: str = "",
    issue_key: str = "",
    attachment_id: str = "",
    name: str = "",
):
    """Return a Jira attachment as a data URL for the Electron renderer."""
    try:
        if issue_key:
            from jira_dashboard.service import fetch_jira_attachment_preview

            content, media_type = await asyncio.to_thread(
                fetch_jira_attachment_preview,
                issue_key,
                attachment_id=attachment_id,
                name=name,
            )
        else:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise HTTPException(status_code=400, detail="Invalid attachment URL.")
            content, media_type = await asyncio.to_thread(_download_jira_attachment_preview, url)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("GET /attachments/preview-data failed")
        raise HTTPException(status_code=502, detail=str(exc) or "Could not load Jira attachment preview.") from exc

    encoded = base64.b64encode(content).decode("ascii")
    return {"dataUrl": f"data:{media_type};base64,{encoded}", "mimeType": media_type}


def _download_jira_attachment_preview(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "image/*,video/*,application/octet-stream;q=0.8,*/*;q=0.5",
            "User-Agent": "LivingColor Desktop",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get_content_type() or "application/octet-stream"
        return response.read(), content_type


@router.post("/connect")
async def connect_jira_dashboard():
    """Ensure the Jira MCP preset is configured and attempt OAuth connection."""
    from jira_dashboard.service import connect_jira_mcp

    try:
        result = await asyncio.to_thread(connect_jira_mcp)
    except Exception as exc:
        logger.exception("POST /connect failed")
        return {
            "ok": False,
            "status": "error",
            "message": str(exc),
            "authenticated": False,
            "toolCount": 0,
        }
    return result
