"""Product-level readiness integration errors."""

from __future__ import annotations


class ReadinessIntegrationError(Exception):
    """Raised when readiness scan cannot reach an external issue source."""
