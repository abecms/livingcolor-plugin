"""Project workspace context for LivingColor Server requests."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

LOCAL_ORG_ID = "local"


@dataclass(frozen=True)
class ProjectContext:
    org_id: str
    project_key: str
    user_id: str | None = None

    def normalized_project_key(self) -> str:
        return (self.project_key or "").strip().upper()

    def normalized_org_id(self) -> str:
        value = (self.org_id or "").strip()
        return value or LOCAL_ORG_ID


_project_context: ContextVar[ProjectContext | None] = ContextVar("livingcolor_project_context", default=None)


def set_project_context(ctx: ProjectContext | None) -> None:
    _project_context.set(ctx)


def get_project_context() -> ProjectContext | None:
    return _project_context.get()


def require_project_context() -> ProjectContext:
    ctx = get_project_context()
    if ctx is None:
        return ProjectContext(org_id=LOCAL_ORG_ID, project_key="")
    return ctx


def parse_project_context_headers(
    *,
    org_id: str | None,
    project_key: str | None,
    user_id: str | None = None,
) -> ProjectContext:
    return ProjectContext(
        org_id=(org_id or "").strip() or LOCAL_ORG_ID,
        project_key=(project_key or "").strip().upper(),
        user_id=(user_id or "").strip() or None,
    )
