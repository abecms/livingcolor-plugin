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


def load_livingcolor_dotenv(*, override: bool = True) -> Path | None:
    """Load ~/.livingcolor/.env so product secrets win over ~/.hermes/.env placeholders."""
    env_path = get_livingcolor_env_path()
    if not env_path.is_file():
        return None

    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.warning("python-dotenv unavailable; skipping LivingColor .env load")
        return None

    load_dotenv(env_path, override=override)
    logger.debug("Loaded LivingColor environment from %s", env_path)
    return env_path


def livingcolor_openrouter_api_key() -> str:
    """Return OPENROUTER_API_KEY preferring ~/.livingcolor/.env over stale Hermes env."""
    load_livingcolor_dotenv(override=True)
    return (os.getenv("OPENROUTER_API_KEY") or "").strip()
