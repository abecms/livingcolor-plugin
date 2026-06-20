"""Publisher agent backend selection for LivingColor delivery."""

from __future__ import annotations

import os
from typing import Any, Protocol


class PublisherAgentBackend(Protocol):
    def execute(self, work_order_id: str, context: dict[str, Any]) -> dict[str, Any]: ...


def get_publisher_agent() -> PublisherAgentBackend:
    backend = os.getenv("LIVINGCOLOR_PUBLISHER_BACKEND", "hermes").strip().lower()
    if backend in {"heuristic", "stub", "deterministic", "direct"}:
        from lc_server.agent_bridge.heuristic_publisher_agent import HeuristicPublisherAgent

        return HeuristicPublisherAgent()

    from lc_server.agent_bridge.hermes_publisher import HermesPublisherAgent

    return HermesPublisherAgent()
