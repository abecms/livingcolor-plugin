"""Hermes-backed LivingColor Analyst Agent."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from delivery_runtime.agents.registry import AgentManifestRegistry
from delivery_runtime.agents.schema import AgentManifest
from delivery_runtime.readiness.analyst_prompt import (
    AnalystParseError,
    build_analyst_user_prompt,
    parse_analyst_completion,
)
from lc_server.agent_bridge.manifest_prompt import render_manifest_system_prompt
from lc_server.integrations.skills import external_guidance_for_skills

logger = logging.getLogger(__name__)

ANALYST_TOOLSETS: list[str] = []
ANALYST_SYSTEM_PROMPT = """You are the LivingColor Analyst Agent.

Your job is to analyze Jira ticket snapshots for autonomous delivery readiness.
This is read-only analysis — never mutate Jira, create Work Orders, or promote tickets.

Apply the readiness scoring rubric and finish with a JSON completion block containing:
readinessScore, readinessStatus, analysisSummary, blockers, recommendedRepos, confidence, estimatedDays.
estimatedDays is your effort estimate in 8-hour workdays as a number, e.g. 1.5.

Always incorporate Jira comments when present. For reopened or re-analyzed tickets, comments
override stale description text and unresolved feedback must surface as blockers.
"""

_registry = AgentManifestRegistry()


class HermesAnalystAgent:
    """Runs the Hermes AIAgent loop for readiness analysis."""

    def __init__(
        self,
        *,
        agent_factory: Callable[..., Any] | None = None,
        registry: AgentManifestRegistry | None = None,
    ) -> None:
        self._agent_factory = agent_factory or _default_analyst_agent_factory
        self._registry = registry or _registry

    def analyze(self, snapshot: dict[str, Any], project_key: str) -> dict[str, Any]:
        key = project_key.strip().upper()
        manifest = _resolve_analyst_manifest(key, registry=self._registry)
        jira_key = str(snapshot.get("key") or "").strip()
        task_id = f"delivery-analyst-{jira_key or key}"
        prompt = build_analyst_user_prompt(snapshot)
        guidance = external_guidance_for_skills(("ticket-analyst",))
        if guidance:
            prompt = f"{prompt}\n\n{guidance}"

        agent = self._agent_factory(
            task_id=task_id,
            jira_key=jira_key,
            project_key=key,
            manifest=manifest,
        )
        result = agent.run_conversation(prompt, task_id=task_id)
        final_response = str(result.get("final_response") or "")
        return parse_analyst_completion(final_response, snapshot)


def _resolve_analyst_manifest(
    project_key: str | None,
    *,
    registry: AgentManifestRegistry,
) -> AgentManifest | None:
    if not project_key:
        return None
    if not registry.is_automation_ready(project_key):
        return None
    return registry.get(project_key, "analyst")


def _default_analyst_agent_factory(
    *,
    task_id: str,
    jira_key: str,
    project_key: str,
    manifest: AgentManifest | None,
) -> Any:
    from hermes_cli.config import load_config
    from hermes_cli.fallback_config import get_fallback_chain
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from lc_server.env_loader import prepare_delivery_agent_environment
    from run_agent import AIAgent

    prepare_delivery_agent_environment()

    os.environ.setdefault("HERMES_YOLO_MODE", "1")
    os.environ.setdefault("HERMES_ACCEPT_HOOKS", "1")

    if manifest:
        system_prompt = render_manifest_system_prompt(manifest)
        toolsets = list(manifest.runtime.toolsets)
        max_iterations = manifest.runtime.max_iterations
        platform = manifest.identity.platform
    else:
        system_prompt = ANALYST_SYSTEM_PROMPT
        toolsets = list(ANALYST_TOOLSETS)
        max_iterations = 15
        platform = "livingcolor-delivery"

    cfg = load_config()
    model_cfg = cfg.get("model") or {}
    if isinstance(model_cfg, str):
        effective_model = model_cfg
        cfg_provider = ""
    else:
        effective_model = str(model_cfg.get("default") or model_cfg.get("model") or "")
        cfg_provider = str(model_cfg.get("provider") or "").strip()

    env_model = os.getenv("HERMES_INFERENCE_MODEL", "").strip()
    env_provider = os.getenv("HERMES_INFERENCE_PROVIDER", "").strip()
    effective_model = env_model or effective_model
    effective_provider = env_provider or cfg_provider or None

    runtime = resolve_runtime_provider(
        requested=effective_provider,
        target_model=effective_model or None,
    )
    fallback = get_fallback_chain(cfg)

    agent = AIAgent(
        api_key=runtime.get("api_key"),
        base_url=runtime.get("base_url"),
        provider=runtime.get("provider"),
        api_mode=runtime.get("api_mode"),
        model=effective_model,
        enabled_toolsets=toolsets,
        max_iterations=max_iterations,
        quiet_mode=True,
        platform=platform,
        session_id=f"delivery-analyst-{jira_key or project_key}",
        ephemeral_system_prompt=system_prompt,
        skip_context_files=True,
        skip_memory=True,
        fallback_model=fallback or None,
        credential_pool=runtime.get("credential_pool"),
        clarify_callback=_analyst_clarify_callback,
    )
    agent.suppress_status_output = True
    agent.stream_delta_callback = None
    agent.tool_gen_callback = None
    return agent


def _analyst_clarify_callback(question: str, choices=None) -> str:
    if choices:
        return (
            f"[LivingColor analyst mode: no human is available. Choose the best option from "
            f"{choices} and continue the readiness analysis.]"
        )
    return (
        "[LivingColor analyst mode: no human is available. Make the most reasonable "
        "assumption and continue the readiness analysis.]"
    )


__all__ = ["AnalystParseError", "HermesAnalystAgent"]
