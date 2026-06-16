"""Hermes-backed LivingColor Sprint Reporter Agent."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

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

Output ONLY the message body text. Do not wrap it in JSON or code fences.
"""

_JSON_BLOCK_RE = re.compile(r"\{[^{}]*\"status\"[^{}]*\}", re.DOTALL)


class SprintReporterError(RuntimeError):
    """Sprint reporter could not produce a message."""


class HermesSprintReporterAgent:
    """Runs a short Hermes AIAgent loop to compose a sprint retrospective message."""

    def __init__(
        self,
        *,
        agent_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._agent_factory = agent_factory or _default_sprint_reporter_agent_factory

    def compose(self, snapshot: dict[str, Any], *, project_key: str) -> str:
        key = project_key.strip().upper()
        sprint_number = snapshot.get("sprintNumber") or snapshot.get("sprint", {}).get("number")
        task_id = f"delivery-sprint-report-{key}-{sprint_number or 'unknown'}"
        prompt = (
            "Compose the sprint retrospective message for this snapshot:\n\n"
            f"{json.dumps(snapshot, indent=2, ensure_ascii=False)}"
        )

        agent = self._agent_factory(task_id=task_id, project_key=key)
        result = agent.run_conversation(prompt, task_id=task_id)
        text = _extract_message_body(str(result.get("final_response") or ""))
        if not text.strip():
            raise SprintReporterError("Sprint reporter returned an empty message")
        return text.strip()


def _extract_message_body(final_response: str) -> str:
    cleaned = final_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    match = _JSON_BLOCK_RE.search(cleaned)
    if match:
        cleaned = cleaned[: match.start()].strip()
    return cleaned


def _default_sprint_reporter_agent_factory(*, task_id: str, project_key: str) -> Any:
    from hermes_cli.config import load_config
    from hermes_cli.fallback_config import get_fallback_chain
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from lc_server.env_loader import prepare_delivery_agent_environment
    from run_agent import AIAgent

    prepare_delivery_agent_environment()

    os.environ.setdefault("HERMES_YOLO_MODE", "1")
    os.environ.setdefault("HERMES_ACCEPT_HOOKS", "1")

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

    return AIAgent(
        api_key=runtime.get("api_key"),
        base_url=runtime.get("base_url"),
        provider=runtime.get("provider"),
        api_mode=runtime.get("api_mode"),
        model=effective_model,
        enabled_toolsets=list(SPRINT_REPORTER_TOOLSETS),
        max_iterations=8,
        quiet_mode=True,
        platform="livingcolor-sprint-reporter",
        session_id=task_id,
        ephemeral_system_prompt=SPRINT_REPORTER_SYSTEM_PROMPT,
        skip_context_files=True,
        skip_memory=True,
        fallback_model=fallback or None,
        credential_pool=runtime.get("credential_pool"),
    )
