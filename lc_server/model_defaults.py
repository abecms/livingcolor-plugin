"""LivingColor fixed model bootstrap."""

from __future__ import annotations

import os

LIVINGCOLOR_FIXED_PROVIDER = "openrouter"
LIVINGCOLOR_FIXED_MODEL = "deepseek/deepseek-v4-pro"

LIVINGCOLOR_DEVELOPER_PROVIDER = "openrouter"
LIVINGCOLOR_DEVELOPER_MODEL = "deepseek/deepseek-v4-pro"


def ensure_livingcolor_fixed_model() -> None:
    """Pin the product default provider/model in Hermes config."""
    from hermes_cli.config import load_config, save_config

    cfg = load_config()
    model_cfg = cfg.get("model")
    if not isinstance(model_cfg, dict):
        model_cfg = {}

    changed = False
    if model_cfg.get("provider") != LIVINGCOLOR_FIXED_PROVIDER:
        model_cfg["provider"] = LIVINGCOLOR_FIXED_PROVIDER
        changed = True
    if model_cfg.get("default") != LIVINGCOLOR_FIXED_MODEL:
        model_cfg["default"] = LIVINGCOLOR_FIXED_MODEL
        changed = True

    if changed:
        cfg["model"] = model_cfg
        save_config(cfg)


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
