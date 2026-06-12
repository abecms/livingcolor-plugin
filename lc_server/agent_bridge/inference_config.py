"""Resolve provider/model for delivery Hermes agents."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from delivery_runtime.agents.schema import AgentManifest


def resolve_delivery_inference(
    *,
    manifest: AgentManifest | None,
    role_default_model: str | None = None,
    role_default_provider: str | None = None,
    allow_env_override: bool = True,
) -> tuple[str, str | None]:
    """Return (model, provider) for a delivery agent run."""
    from hermes_cli.config import load_config

    cfg = load_config()
    model_cfg = cfg.get("model") or {}
    if isinstance(model_cfg, str):
        global_model = model_cfg
        global_provider = ""
    else:
        global_model = str(model_cfg.get("default") or model_cfg.get("model") or "")
        global_provider = str(model_cfg.get("provider") or "").strip()

    manifest_model = ""
    manifest_provider = ""
    if manifest is not None:
        manifest_model = str(manifest.runtime.model or "").strip()
        manifest_provider = str(manifest.runtime.provider or "").strip()

    effective_model = manifest_model or role_default_model or global_model
    effective_provider = manifest_provider or role_default_provider or global_provider or None

    if allow_env_override:
        env_model = os.getenv("HERMES_INFERENCE_MODEL", "").strip()
        env_provider = os.getenv("HERMES_INFERENCE_PROVIDER", "").strip()
        if env_model:
            effective_model = env_model
        if env_provider:
            effective_provider = env_provider

    return effective_model, effective_provider or None
