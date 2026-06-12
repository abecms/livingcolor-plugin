"""Developer agent backend selection for LivingColor delivery."""

from __future__ import annotations

import os
from typing import Any, Protocol


class DeveloperAgentBackend(Protocol):
    def execute(self, work_order_id: str, context: dict[str, Any]) -> dict[str, Any]: ...


def get_developer_agent() -> DeveloperAgentBackend:
    backend = os.getenv("LIVINGCOLOR_DEVELOPER_BACKEND", "hermes").strip().lower()
    if backend in {"heuristic", "stub", "deterministic"}:
        from delivery_runtime.development.developer_agent import HeuristicDeveloperAgent

        return HeuristicDeveloperAgent()

    from lc_server.agent_bridge.hermes_developer import HermesDeveloperAgent

    return HermesDeveloperAgent()
