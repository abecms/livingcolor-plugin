"""LivingColor production shadow mode helpers (Hermes-free)."""

from __future__ import annotations

import os


def is_shadow_mode() -> bool:
    return os.getenv("LIVINGCOLOR_SHADOW_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def should_keep_workspace() -> bool:
    return os.getenv("LIVINGCOLOR_KEEP_WORKSPACE", "").strip().lower() in {"1", "true", "yes", "on"}


def shadow_mode_label() -> str:
    return "shadow" if is_shadow_mode() else "standard"
