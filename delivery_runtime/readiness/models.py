"""Readiness record domain models."""

from __future__ import annotations

from typing import Literal

ReadinessStatus = Literal[
    "pending_analysis",
    "analyzed",
    "ready",
    "not_ready",
    "promoted",
    "dismissed",
]
