"""Planner agent backend selection for LivingColor delivery."""

from __future__ import annotations

from typing import Any, Protocol

from delivery_runtime.context.models import ContextPack
from delivery_runtime.context.planner import RepoAwarePlanner
from lc_server.agent_bridge.agent_backend import is_heuristic_backend
from lc_server.agent_bridge.hermes_planner import HermesPlannerAgent


class PlannerAgentBackend(Protocol):
    def plan(self, pack: ContextPack, *, project_key: str) -> dict[str, Any]: ...


class _HeuristicPlannerBackend:
    def plan(self, pack: ContextPack, *, project_key: str) -> dict[str, Any]:
        del project_key
        return RepoAwarePlanner().plan(pack)


def get_planner_agent() -> PlannerAgentBackend:
    if is_heuristic_backend("planner"):
        return _HeuristicPlannerBackend()
    return HermesPlannerAgent()
