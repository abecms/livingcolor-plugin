"""Environment helpers for LivingColor FAST DEV mode."""

from __future__ import annotations

import os


def is_fast_dev_mode() -> bool:
    """Return True when expensive validation pipelines should be skipped."""
    return os.getenv("LIVINGCOLOR_FAST_DEV", "").strip().lower() in {"1", "true", "yes", "on"}


def is_truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}
