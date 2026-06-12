"""Work Order domain models."""

from __future__ import annotations

from typing import Literal

WorkOrderStatus = Literal[
    "intake",
    "running",
    "awaiting_gate",
    "completed",
    "failed",
    "cancelled",
]

WorkOrderStage = Literal[
    "intake",
    "analysis_review",
    "development",
    "mr_review",
    "mr_publication",
    "jira_review",
    "completed",
]
