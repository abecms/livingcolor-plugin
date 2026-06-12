"""Resolve the active Jira project key for the current HTTP request."""

from __future__ import annotations

from typing import Any


def resolve_request_project_key(request: Any | None = None) -> str | None:
    try:
        from lc_server.context import get_project_context

        ctx = get_project_context()
        if ctx is not None:
            key = ctx.normalized_project_key()
            if key:
                return key
    except ImportError:
        pass

    if request is not None:
        headers = getattr(request, "headers", None)
        if headers is not None:
            header = (headers.get("x-lc-project-key") or "").strip().upper()
            if header:
                return header
    return None


def try_activate_local_project(project_key: str | None) -> None:
    key = (project_key or "").strip().upper()
    if not key:
        return
    try:
        from delivery_runtime.automation.local_projects import activate_local_project

        activate_local_project(key)
    except (ImportError, ValueError):
        return
