"""Hermes async subagent backend for LivingColor Analyst runs."""

from __future__ import annotations

import asyncio
import importlib.util
from collections.abc import Awaitable, Callable
from typing import Any

from delivery_runtime.agents.registry import AgentManifestRegistry
from delivery_runtime.readiness.analyst_prompt import (
    build_analyst_user_prompt,
    parse_analyst_completion,
)
from lc_server.integrations.jira_attachment_extract import enrich_snapshot_with_attachment_extracts
from lc_server.integrations.skills import (
    EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER,
    external_guidance_for_skills,
)

SubagentLauncher = Callable[..., Awaitable[Any]]
FallbackRunner = Callable[[dict[str, Any], str], dict[str, Any]]


class HermesSubagentAnalystBackend:
    name = "hermes_subagent"

    def __init__(
        self,
        *,
        launcher: SubagentLauncher | None = None,
        fallback_runner: FallbackRunner | None = None,
        registry: AgentManifestRegistry | None = None,
    ) -> None:
        self._launcher = launcher or _default_subagent_launcher
        self._fallback_runner = fallback_runner
        self._registry = registry or AgentManifestRegistry()

    async def analyze_ticket(
        self,
        snapshot: dict[str, Any],
        *,
        project_key: str,
        run_id: str,
    ) -> dict[str, Any]:
        key = project_key.strip().upper()
        enriched_snapshot = enrich_snapshot_with_attachment_extracts(snapshot)
        if self._fallback_runner is not None and not self._registry.is_automation_ready(key):
            return await asyncio.to_thread(self._fallback_runner, enriched_snapshot, key)

        jira_key = str(enriched_snapshot.get("key") or "").strip()
        task_id = f"delivery-analyst-{jira_key or key}-{run_id}"
        prompt = build_analyst_user_prompt(enriched_snapshot)
        guidance = external_guidance_for_skills(("ticket-analyst",))
        if guidance:
            prompt = f"{prompt}\n\n{guidance}\n\n{EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER}"

        result = await self._launcher(
            task_id=task_id,
            prompt=prompt,
            project_key=key,
        )
        return parse_analyst_completion(_extract_subagent_final_response(result), enriched_snapshot)


def default_subagent_launcher_available() -> bool:
    """Return whether the native Hermes subagent launcher can be imported."""
    try:
        return importlib.util.find_spec("hermes_cli.subagents") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _extract_subagent_final_response(result: Any) -> str:
    if isinstance(result, dict):
        return str(result.get("final_response") or result.get("finalResponse") or "")
    return str(result or "")


async def _default_subagent_launcher(*, task_id: str, prompt: str, project_key: str) -> str:
    """Launch a read-only Hermes analyst subagent and return its final response."""
    from hermes_cli.subagents import run_subagent

    result = await run_subagent(
        task_id=task_id,
        prompt=prompt,
        readonly=True,
        model=None,
        metadata={"projectKey": project_key, "role": "analyst"},
    )
    return _extract_subagent_final_response(result)
