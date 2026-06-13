"""Same-origin proxy to the LivingColor cloud API (avoids browser CORS from Hermes tab)."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["cloud-proxy"])

_CLOUD_API_BASE = os.getenv("LIVINGCOLOR_CLOUD_API_URL", "https://api-livingcolor.visualq.ai").rstrip("/")

_FORWARD_HEADERS = (
    "authorization",
    "content-type",
    "x-lc-org-id",
    "x-org-id",
    "x-lc-project-key",
)


def _build_upstream_url(path: str) -> str:
    cleaned = path.lstrip("/")
    return f"{_CLOUD_API_BASE}/{cleaned}"


def _proxy_request(method: str, path: str, headers: dict[str, str], body: bytes | None) -> tuple[int, dict[str, str], bytes]:
    url = _build_upstream_url(path)
    request = urllib.request.Request(url, data=body, method=method.upper())
    for key, value in headers.items():
        if value:
            request.add_header(key, value)

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_headers = {
                key: value
                for key, value in response.headers.items()
                if key.lower() == "content-type"
            }
            return response.status, response_headers, response.read()
    except urllib.error.HTTPError as exc:
        response_headers = {
            key: value
            for key, value in exc.headers.items()
            if key.lower() == "content-type"
        }
        return exc.code, response_headers, exc.read()


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_cloud_api(path: str, request: Request) -> Response:
    """Forward plugin team-mode calls to api-livingcolor.visualq.ai server-side."""
    if request.method == "OPTIONS":
        return Response(status_code=204)

    body = await request.body()
    forward_headers: dict[str, str] = {}
    for name in _FORWARD_HEADERS:
        value = request.headers.get(name)
        if value:
            forward_headers[name] = value

    status, upstream_headers, payload = _proxy_request(request.method, path, forward_headers, body or None)
    if status >= 500:
        logger.warning("Cloud proxy %s %s -> %s", request.method, path, status)

    media_type = upstream_headers.get("Content-Type", "application/json")
    return Response(content=payload, status_code=status, media_type=media_type)
