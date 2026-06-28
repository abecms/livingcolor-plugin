"""Hermes-backed LivingColor Planner Agent for Gate 1 implementation plans."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from delivery_runtime.agents.registry import AgentManifestRegistry
from delivery_runtime.agents.schema import AgentManifest
from delivery_runtime.context.models import ContextPack
from delivery_runtime.context.planner_prompt import (
    PlannerParseError,
    build_planner_user_prompt,
    parse_planner_completion,
)
from lc_server.agent_bridge.manifest_prompt import render_manifest_system_prompt

logger = logging.getLogger(__name__)

PLANNER_TOOLSETS: list[str] = ["file", "skills"]
PLANNER_SYSTEM_PROMPT = """You are the LivingColor Planner Agent.

Your job is to produce Gate 1 implementation plans for Jira tickets before developer handoff.
This is read-only planning — never edit files, push commits, open MRs, or mutate Jira.

Read the full ticket: title, description, comments, and attachment extracts. Heuristic
candidate file lists may be wrong (token overlap false positives). Derive impacted files
from the actual feature area described in the ticket.

When a local repository checkout is available, use read-only file tools to verify paths.

Always finish with a JSON completion block containing:
needsClarification, clarificationReason, ticketUnderstanding, targetRepo,
implementationPlan, likelyImpactedFiles, risks, confidenceLevel.
"""

_registry = AgentManifestRegistry()


class HermesPlannerAgent:
    """Runs the Hermes AIAgent loop for Gate 1 implementation planning."""

    def __init__(
        self,
        *,
        agent_factory: Callable[..., Any] | None = None,
        registry: AgentManifestRegistry | None = None,
    ) -> None:
        self._agent_factory = agent_factory or _default_planner_agent_factory
        self._registry = registry or _registry

    def plan(self, pack: ContextPack, *, project_key: str) -> dict[str, Any]:
        if not pack.repo_resolved:
            return {
                "needsClarification": True,
                "clarificationReason": (
                    f"No repository could be identified for project "
                    f"{pack.jira_ticket.get('projectKey')}. Update project_mapping.yaml "
                    f"or provide a resolved repo before planning."
                ),
                "contextPack": pack.to_dict(),
            }

        key = project_key.strip().upper()
        manifest = _resolve_planner_manifest(key, registry=self._registry)
        jira_key = pack.jira_key.strip()
        task_id = f"delivery-planner-{jira_key or key}"
        prompt = build_planner_user_prompt(pack)

        agent = self._agent_factory(
            task_id=task_id,
            jira_key=jira_key,
            project_key=key,
            manifest=manifest,
            repo_checkout_path=pack.repo_checkout_path,
        )
        result = agent.run_conversation(prompt, task_id=task_id)
        final_response = str(result.get("final_response") or "")
        return parse_planner_completion(final_response, pack)


def _resolve_planner_manifest(
    project_key: str | None,
    *,
    registry: AgentManifestRegistry,
) -> AgentManifest | None:
    if not project_key:
        return None
    if not registry.is_automation_ready(project_key):
        return None
    return registry.get(project_key, "planner")


def _default_planner_agent_factory(
    *,
    task_id: str,
    jira_key: str,
    project_key: str,
    manifest: AgentManifest | None,
    repo_checkout_path: str | None = None,
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
        system_prompt = PLANNER_SYSTEM_PROMPT
        toolsets = list(PLANNER_TOOLSETS)
        max_iterations = 20
        platform = "livingcolor-delivery"

    from lc_server.agent_bridge.inference_config import resolve_delivery_inference
    from lc_server.model_defaults import (
        LIVINGCOLOR_PLANNER_MODEL,
        LIVINGCOLOR_PLANNER_PROVIDER,
    )

    effective_model, effective_provider = resolve_delivery_inference(
        manifest=manifest,
        role_default_model=LIVINGCOLOR_PLANNER_MODEL,
        role_default_provider=LIVINGCOLOR_PLANNER_PROVIDER,
        allow_env_override=True,
    )

    cfg = load_config()
    runtime = resolve_runtime_provider(
        requested=effective_provider,
        target_model=effective_model or None,
    )
    fallback = get_fallback_chain(cfg)

    if repo_checkout_path and os.path.isdir(repo_checkout_path):
        logger.debug("Planner checkout available at %s (file tools use repo-relative paths)", repo_checkout_path)

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
        session_id=f"delivery-planner-{jira_key or project_key}",
        ephemeral_system_prompt=system_prompt,
        skip_context_files=True,
        skip_memory=True,
        fallback_model=fallback or None,
        credential_pool=runtime.get("credential_pool"),
        clarify_callback=_planner_clarify_callback,
    )
    agent.suppress_status_output = True
    agent.stream_delta_callback = None
    agent.tool_gen_callback = None
    return agent


def _planner_clarify_callback(question: str, choices=None) -> str:
    if choices:
        return (
            f"[LivingColor planner mode: no human is available. Choose the best option from "
            f"{choices} and continue the implementation plan.]"
        )
    return (
        "[LivingColor planner mode: no human is available. Make the most reasonable "
        "assumption and continue the implementation plan.]"
    )


__all__ = ["HermesPlannerAgent", "PlannerParseError"]
