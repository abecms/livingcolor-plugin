"""LivingColor per-role OpenRouter model defaults for delivery agents."""

from __future__ import annotations

import os

LIVINGCOLOR_PROVIDER = "openrouter"

# Orchestration-oriented roles: Jira analysis, Gate 1 planning, sprint documentation.
LIVINGCOLOR_ORCHESTRATION_MODEL = "openrouter/owl-alpha"
LIVINGCOLOR_ORCHESTRATION_PROVIDER = LIVINGCOLOR_PROVIDER

LIVINGCOLOR_ANALYST_MODEL = LIVINGCOLOR_ORCHESTRATION_MODEL
LIVINGCOLOR_ANALYST_PROVIDER = LIVINGCOLOR_ORCHESTRATION_PROVIDER
LIVINGCOLOR_PLANNER_MODEL = LIVINGCOLOR_ORCHESTRATION_MODEL
LIVINGCOLOR_PLANNER_PROVIDER = LIVINGCOLOR_ORCHESTRATION_PROVIDER
LIVINGCOLOR_REPORTER_MODEL = LIVINGCOLOR_ORCHESTRATION_MODEL
LIVINGCOLOR_REPORTER_PROVIDER = LIVINGCOLOR_ORCHESTRATION_PROVIDER

# Code generation and mutating delivery roles.
LIVINGCOLOR_DEVELOPER_MODEL = "deepseek/deepseek-v4-pro"
LIVINGCOLOR_DEVELOPER_PROVIDER = LIVINGCOLOR_PROVIDER
LIVINGCOLOR_PUBLISHER_MODEL = LIVINGCOLOR_DEVELOPER_MODEL
LIVINGCOLOR_PUBLISHER_PROVIDER = LIVINGCOLOR_PROVIDER

# Optional per-project override for frontend-heavy repos (set in developer manifest).
LIVINGCOLOR_FRONTEND_MODEL = "z-ai/glm-5.2"
LIVINGCOLOR_FRONTEND_PROVIDER = LIVINGCOLOR_PROVIDER

# Legacy aliases kept for callers that imported the old names.
LIVINGCOLOR_FIXED_PROVIDER: str | None = None
LIVINGCOLOR_FIXED_MODEL: str | None = None


def ensure_livingcolor_fixed_model() -> None:
    """No-op — Hermes user config is the fallback when manifests omit model/provider."""


def is_delivery_llm_available() -> bool:
    """Return True if the delivery LLM provider/model can be resolved without error."""
    try:
        from hermes_cli.config import load_config
        from hermes_cli.runtime_provider import resolve_runtime_provider

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
        return bool(runtime)
    except Exception:
        return False
