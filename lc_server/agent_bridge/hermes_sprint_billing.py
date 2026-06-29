"""Hermes-backed sprint billing proposal agent."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

SPRINT_BILLING_SYSTEM_PROMPT = """You are the LivingColor Sprint Billing Agent.

Build a Stripe invoice proposal from the provided sprint billing snapshot.

Rules:
- Output ONLY valid JSON.
- Use only done tickets from the snapshot.
- Do not invent ticket keys, quantities, currency, customer IDs, or prices.
- You may group done tickets into one line when the description remains clear.
- Every billable done ticket must appear exactly once.
- Keep descriptions concise and client-ready.
"""

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class SprintBillingAgentError(RuntimeError):
    """Sprint billing agent could not produce a valid proposal."""


class HermesSprintBillingAgent:
    def __init__(self, *, agent_factory: Callable[..., Any] | None = None) -> None:
        self._agent_factory = agent_factory or _default_sprint_billing_agent_factory

    def propose(self, billing_snapshot: dict[str, Any], *, project_key: str) -> dict[str, Any]:
        key = project_key.strip().upper()
        task_id = f"delivery-sprint-billing-{key}-{billing_snapshot.get('dedupKey') or 'unknown'}"
        prompt = (
            f"{SPRINT_BILLING_SYSTEM_PROMPT}\n\n"
            "Sprint billing snapshot:\n"
            f"{json.dumps(billing_snapshot, indent=2, ensure_ascii=False)}"
        )
        agent = self._agent_factory(task_id=task_id, project_key=key)
        result = agent.run_conversation(prompt, task_id=task_id)
        raw = str(result.get("final_response") or "").strip()
        cleaned = _JSON_FENCE_RE.sub("", raw).strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise SprintBillingAgentError("Sprint billing agent returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise SprintBillingAgentError("Sprint billing agent proposal must be a JSON object")
        return parsed


def _default_sprint_billing_agent_factory(*, task_id: str, project_key: str) -> Any:
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

    effective_model = os.getenv("HERMES_INFERENCE_MODEL", "").strip() or effective_model
    effective_provider = os.getenv("HERMES_INFERENCE_PROVIDER", "").strip() or cfg_provider or None
    runtime = resolve_runtime_provider(requested=effective_provider, target_model=effective_model or None)

    return AIAgent(
        api_key=runtime.get("api_key"),
        base_url=runtime.get("base_url"),
        provider=runtime.get("provider"),
        api_mode=runtime.get("api_mode"),
        model=effective_model,
        enabled_toolsets=[],
        max_iterations=6,
        quiet_mode=True,
        platform="livingcolor-sprint-billing",
        session_id=task_id,
        ephemeral_system_prompt=SPRINT_BILLING_SYSTEM_PROMPT,
        skip_context_files=True,
        skip_memory=True,
        fallback_model=get_fallback_chain(cfg) or None,
        credential_pool=runtime.get("credential_pool"),
    )
