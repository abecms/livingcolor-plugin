"""FastAPI middleware for LivingColor project context."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from lc_server.context import (
    parse_project_context_headers,
    reset_project_context,
    reset_request_bearer_token,
    set_project_context,
    set_request_bearer_token,
)
from lc_server.integrations.firebase_auth import extract_bearer_token
from lc_server.integrations.project_mcp_runtime import apply_project_mcp_runtime


class ProjectContextMiddleware(BaseHTTPMiddleware):
    """Attach ProjectContext from headers for the duration of each request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        org_id = request.headers.get("x-lc-org-id") or request.headers.get("x-org-id")
        project_key = request.headers.get("x-lc-project-key")
        token_uid = getattr(request.state, "firebase_uid", None)
        ctx = parse_project_context_headers(
            org_id=org_id,
            project_key=project_key,
            user_id=token_uid,
        )
        context_token = set_project_context(ctx)
        auth_token = set_request_bearer_token(extract_bearer_token(request.headers.get("authorization")))
        try:
            if ctx.normalized_project_key():
                from delivery_runtime.automation.project_context import try_activate_local_project

                try_activate_local_project(ctx.normalized_project_key())
                apply_project_mcp_runtime(ctx.normalized_project_key())
            return await call_next(request)
        finally:
            reset_request_bearer_token(auth_token)
            reset_project_context(context_token)
