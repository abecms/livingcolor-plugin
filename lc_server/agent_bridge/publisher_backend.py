"""Publisher agent backend selection for LivingColor delivery."""

from __future__ import annotations

from typing import Any, Protocol

from lc_server.agent_bridge.agent_backend import is_heuristic_backend
from lc_server.agent_bridge.heuristic_publisher import HeuristicPublisherAgent
from lc_server.agent_bridge.hermes_publisher import HermesPublisherAgent


class PublisherAgentBackend(Protocol):
    def execute(self, work_order_id: str, context: dict[str, Any]) -> dict[str, Any]: ...


def get_publisher_agent() -> PublisherAgentBackend:
    if is_heuristic_backend("publisher"):
        return HeuristicPublisherAgent()
    return HermesPublisherAgent()
