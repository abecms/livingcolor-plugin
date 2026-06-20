"""Cloud-runner backend selection for delivery agent roles."""

from __future__ import annotations

import os

_HEURISTIC_ALIASES = frozenset({"heuristic", "stub", "deterministic"})


def is_heuristic_backend(role: str) -> bool:
    """Return True when a delivery role should use deterministic/heuristic logic."""
    env_name = f"LIVINGCOLOR_{role.strip().upper()}_BACKEND"
    return os.getenv(env_name, "").strip().lower() in _HEURISTIC_ALIASES
