"""LivingColor fixed model bootstrap."""

from __future__ import annotations

import os

LIVINGCOLOR_FIXED_PROVIDER: str | None = None
LIVINGCOLOR_FIXED_MODEL: str | None = None
LIVINGCOLOR_DEVELOPER_PROVIDER: str | None = None
LIVINGCOLOR_DEVELOPER_MODEL: str | None = None


def ensure_livingcolor_fixed_model() -> None:
    """No-op — Hermes user config is the sole source of truth."""


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
