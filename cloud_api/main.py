"""LivingColor cloud API entrypoint for api-livingcolor.visualq.ai."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cloud_api.routes import events, locks, orgs, projects, reconcile, session

_DEFAULT_CORS_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://api-livingcolor.visualq.ai",
    "https://visualq.ai",
]


def _cors_origins() -> list[str]:
    extra = os.getenv("LC_CORS_ORIGINS", "").strip()
    origins = list(_DEFAULT_CORS_ORIGINS)
    if extra:
        origins.extend(part.strip() for part in extra.split(",") if part.strip())
    return origins


app = FastAPI(title="LivingColor Cloud API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "livingcolor-cloud"}


app.include_router(session.router, prefix="/v1")
app.include_router(orgs.router, prefix="/v1")
app.include_router(projects.router, prefix="/v1")
app.include_router(locks.router, prefix="/v1")
app.include_router(events.router, prefix="/v1")
app.include_router(reconcile.router, prefix="/v1")
