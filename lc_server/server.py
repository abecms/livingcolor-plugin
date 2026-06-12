"""LivingColor Server — product HTTP host."""

from __future__ import annotations

import os


def create_app():
    """Return the FastAPI application with LivingColor middleware."""
    os.environ.setdefault("LIVINGCOLOR_API_ONLY", "1")
    from hermes_cli.web_server import app as fastapi_app
    from lc_server.middleware import ProjectContextMiddleware

    fastapi_app.add_middleware(ProjectContextMiddleware)
    return fastapi_app


def start_server(
    host: str = "127.0.0.1",
    port: int = 9119,
    open_browser: bool = False,
    allow_public: bool = False,
) -> None:
    """Start the LivingColor API server (desktop backend)."""
    os.environ.setdefault("LIVINGCOLOR_API_ONLY", "1")
    from hermes_cli.web_server import start_server as _legacy_start

    _legacy_start(host=host, port=port, open_browser=open_browser, allow_public=allow_public)
