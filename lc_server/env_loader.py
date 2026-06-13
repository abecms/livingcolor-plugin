"""LivingColor product environment loading."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_INFERENCE_ENV_KEYS = frozenset(
    {
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "HERMES_INFERENCE_MODEL",
        "HERMES_INFERENCE_PROVIDER",
    }
)


def get_livingcolor_env_path() -> Path:
    from lc_constants import get_livingcolor_home

    return get_livingcolor_home() / ".env"


def _livingcolor_env_candidates() -> list[Path]:
    """Plugin home first, then legacy product home (~/.livingcolor)."""
    paths = [get_livingcolor_env_path()]
    override = os.environ.get("LIVINGCOLOR_HOME", "").strip()
    if override:
        paths.insert(0, Path(override).expanduser() / ".env")
    legacy = Path.home() / ".livingcolor" / ".env"
    if legacy not in paths:
        paths.append(legacy)
    return paths


def _preserve_inference_env() -> dict[str, str]:
    return {key: os.environ[key] for key in _INFERENCE_ENV_KEYS if os.environ.get(key)}


def _restore_inference_env(preserved: dict[str, str]) -> None:
    for key, value in preserved.items():
        os.environ[key] = value


def load_livingcolor_dotenv(*, override: bool = True) -> Path | None:
    """Load LivingColor .env files for product-specific secrets.

    Inference provider, model, and API keys already resolved by Hermes are
    preserved so delivery agents honor the user's Hermes provider selection.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.warning("python-dotenv unavailable; skipping LivingColor .env load")
        return None

    loaded: Path | None = None
    for env_path in _livingcolor_env_candidates():
        if not env_path.is_file():
            continue
        preserved = _preserve_inference_env()
        load_dotenv(env_path, override=override)
        _restore_inference_env(preserved)
        loaded = env_path
        logger.debug("Loaded LivingColor environment from %s", env_path)
    return loaded


def prepare_delivery_agent_environment() -> None:
    """Load Hermes credentials and LivingColor product env for delivery agents."""
    try:
        from hermes_cli.config import reload_env

        reload_env()
    except Exception as exc:
        logger.warning("Could not reload Hermes environment: %s", exc)
    load_livingcolor_dotenv(override=True)


def livingcolor_openrouter_api_key() -> str:
    """Return OPENROUTER_API_KEY from the prepared delivery agent environment."""
    prepare_delivery_agent_environment()
    return (os.getenv("OPENROUTER_API_KEY") or "").strip()
