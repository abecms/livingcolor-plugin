"""Planner agent backend selection for LivingColor delivery."""

from __future__ import annotations

import os
from typing import Any, Protocol

from delivery_runtime.context.models import ContextPack


class PlannerAgentBackend(Protocol):
    def plan(self, pack: ContextPack, *, project_key: str) -> dict[str, Any]: ...


class HeuristicPlannerAgent:
    """Deterministic Gate 1 planner for tests and offline environments."""

    def plan(self, pack: ContextPack, *, project_key: str) -> dict[str, Any]:
        from delivery_runtime.context.planner import RepoAwarePlanner

        return RepoAwarePlanner().plan(pack)


def get_planner_agent() -> PlannerAgentBackend:
    backend = os.getenv("LIVINGCOLOR_PLANNER_BACKEND", "hermes").strip().lower()
    if backend in {"heuristic", "stub", "deterministic"}:
        return HeuristicPlannerAgent()

    from lc_server.agent_bridge.hermes_planner import HermesPlannerAgent

    return HermesPlannerAgent()
