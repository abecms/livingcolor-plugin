"""Hermes-backed LivingColor Sprint Reporter Agent."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

from delivery_runtime.agents.registry import AgentManifestRegistry
from delivery_runtime.agents.schema import AgentManifest
from lc_server.agent_bridge.manifest_prompt import render_manifest_system_prompt
from lc_server.integrations.skills import (
    EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER,
    external_guidance_for_skills,
)

logger = logging.getLogger(__name__)

SPRINT_REPORTER_TOOLSETS: list[str] = []
SPRINT_REPORTER_SYSTEM_PROMPT = """You are the LivingColor Sprint Reporter Agent.

Write a concise sprint retrospective for the engineering team based on the JSON snapshot.
The message will be posted to the project's Hermes messaging channel (Slack, etc.).

Rules:
- Use Slack-compatible mrkdwn (*bold*, _italic_, bullet lists).
- Include: sprint name, date range, planned capacity, tickets planned vs delivered,
  work order outcomes, notable wins, blockers, and carry-over items.
- Be factual — only use data from the snapshot.
- Keep the message under 3500 characters.
- Write in the language given by communicationLanguage in the snapshot.
- If billing.invoiceUrl is present, include the Stripe invoice link in a short billing line.
- If billing.warning is present and billing.invoiceUrl is absent, include the invoice warning factually.

Output ONLY the message body text. Do not wrap it in JSON or code fences.
"""

_registry = AgentManifestRegistry()
_JSON_BLOCK_RE = re.compile(r"\{[^{}]*\"status\"[^{}]*\}", re.DOTALL)


class SprintReporterError(RuntimeError):
    """Sprint reporter could not produce a message."""


class HermesSprintReporterAgent:
    """Runs a short Hermes AIAgent loop to compose a sprint retrospective message."""

    def __init__(
        self,
        *,
        agent_factory: Callable[..., Any] | None = None,
        registry: AgentManifestRegistry | None = None,
    ) -> None:
        self._agent_factory = agent_factory or _default_sprint_reporter_agent_factory
        self._registry = registry or _registry

    def compose(self, snapshot: dict[str, Any], *, project_key: str) -> str:
        key = project_key.strip().upper()
        manifest = _resolve_reporter_manifest(key, registry=self._registry)
        sprint_number = snapshot.get("sprintNumber") or snapshot.get("sprint", {}).get("number")
        task_id = f"delivery-sprint-report-{key}-{sprint_number or 'unknown'}"
        prompt = (
            "Compose the sprint retrospective message for this snapshot:\n\n"
            f"{json.dumps(snapshot, indent=2, ensure_ascii=False)}"
        )
        guidance = external_guidance_for_skills(("sprint-reporter",))
        if guidance:
            prompt = f"{prompt}\n\n{guidance}\n\n{EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER}"

        agent = self._agent_factory(
            task_id=task_id,
            project_key=key,
            manifest=manifest,
        )
        result = agent.run_conversation(prompt, task_id=task_id)
        text = _extract_message_body(str(result.get("final_response") or ""))
        if not text.strip():
            raise SprintReporterError("Sprint reporter returned an empty message")
        return text.strip()


def _resolve_reporter_manifest(
    project_key: str | None,
    *,
    registry: AgentManifestRegistry,
) -> AgentManifest | None:
    if not project_key:
        return None
    if not registry.is_automation_ready(project_key):
        return None
    return registry.get(project_key, "reporter")


def _extract_message_body(final_response: str) -> str:
    cleaned = final_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    match = _JSON_BLOCK_RE.search(cleaned)
    if match:
        cleaned = cleaned[: match.start()].strip()
    return cleaned


def _default_sprint_reporter_agent_factory(
    *,
    task_id: str,
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
        system_prompt = SPRINT_REPORTER_SYSTEM_PROMPT
        toolsets = list(SPRINT_REPORTER_TOOLSETS)
        max_iterations = 8
        platform = "livingcolor-sprint-reporter"

    from lc_server.agent_bridge.inference_config import resolve_delivery_inference
    from lc_server.model_defaults import (
        LIVINGCOLOR_REPORTER_MODEL,
        LIVINGCOLOR_REPORTER_PROVIDER,
    )

    effective_model, effective_provider = resolve_delivery_inference(
        manifest=manifest,
        role_default_model=LIVINGCOLOR_REPORTER_MODEL,
        role_default_provider=LIVINGCOLOR_REPORTER_PROVIDER,
        allow_env_override=True,
    )

    cfg = load_config()
    runtime = resolve_runtime_provider(
        requested=effective_provider,
        target_model=effective_model or None,
    )
    fallback = get_fallback_chain(cfg)

    return AIAgent(
        api_key=runtime.get("api_key"),
        base_url=runtime.get("base_url"),
        provider=runtime.get("provider"),
        api_mode=runtime.get("api_mode"),
        model=effective_model,
        enabled_toolsets=toolsets,
        max_iterations=max_iterations,
        quiet_mode=True,
        platform=platform,
        session_id=task_id,
        ephemeral_system_prompt=system_prompt,
        skip_context_files=True,
        skip_memory=True,
        fallback_model=fallback or None,
        credential_pool=runtime.get("credential_pool"),
    )


__all__ = ["HermesSprintReporterAgent", "SprintReporterError"]
