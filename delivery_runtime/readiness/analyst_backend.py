"""Analyst LLM backend interfaces."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol


class AnalystBackend(Protocol):
    name: str

    async def analyze_ticket(
        self,
        snapshot: dict[str, Any],
        *,
        project_key: str,
        run_id: str,
    ) -> dict[str, Any]:
        ...


class SynchronousAnalystBackend:
    """Adapter for legacy synchronous analyst callables."""

    name = "hermes_conversation"

    def __init__(self, runner: Callable[[dict[str, Any], str], dict[str, Any]]) -> None:
        self._runner = runner

    async def analyze_ticket(
        self,
        snapshot: dict[str, Any],
        *,
        project_key: str,
        run_id: str,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._runner, snapshot, project_key)
