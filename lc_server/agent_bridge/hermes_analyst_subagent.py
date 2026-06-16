"""Hermes async subagent backend for LivingColor Analyst runs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from delivery_runtime.readiness.analyst_prompt import (
    build_analyst_user_prompt,
    parse_analyst_completion,
)
from lc_server.integrations.skills import (
    EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER,
    external_guidance_for_skills,
)

SubagentLauncher = Callable[..., Awaitable[str]]


class HermesSubagentAnalystBackend:
    name = "hermes_subagent"

    def __init__(self, *, launcher: SubagentLauncher | None = None) -> None:
        self._launcher = launcher or _default_subagent_launcher

    async def analyze_ticket(
        self,
        snapshot: dict[str, Any],
        *,
        project_key: str,
        run_id: str,
    ) -> dict[str, Any]:
        jira_key = str(snapshot.get("key") or "").strip()
        task_id = f"delivery-analyst-{jira_key or project_key}-{run_id}"
        prompt = build_analyst_user_prompt(snapshot)
        guidance = external_guidance_for_skills(("ticket-analyst",))
        if guidance:
            prompt = f"{prompt}\n\n{guidance}\n\n{EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER}"

        final_response = await self._launcher(
            task_id=task_id,
            prompt=prompt,
            project_key=project_key.strip().upper(),
        )
        return parse_analyst_completion(str(final_response or ""), snapshot)


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
    if isinstance(result, dict):
        return str(result.get("final_response") or result.get("finalResponse") or "")
    return str(result or "")
