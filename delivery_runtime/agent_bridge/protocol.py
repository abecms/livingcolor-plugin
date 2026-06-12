"""Replaceable agent execution adapter protocol."""

from __future__ import annotations

from typing import Any, Protocol


class AgentRuntimeBridge(Protocol):
    """Product-facing adapter to an agent runtime (Hermes today, swappable)."""

    async def run_readiness_analysis(self, jira_key: str, context: dict[str, Any]) -> dict[str, Any]: ...

    async def run_node(self, work_order_id: str, node: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]: ...

    async def cancel(self, run_id: str) -> None: ...


# Backward-compatible alias for in-flight docs and tests.
AgentBridge = AgentRuntimeBridge
