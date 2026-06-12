"""Best-effort Jira originalEstimate write-back (Hermes-free domain logic)."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from delivery_runtime.jira.estimation_format import days_to_jira_estimate
from delivery_runtime.shadow.mode import is_shadow_mode

logger = logging.getLogger(__name__)


class JiraEstimateInvoker(Protocol):
    def get_issue(self, issue_key: str) -> dict[str, Any]: ...

    def update_estimate(self, issue_key: str, estimate: str) -> None: ...


def write_estimate_to_jira(
    issue_key: str,
    estimated_days: float | None,
    *,
    invoker: JiraEstimateInvoker,
) -> dict[str, Any]:
    """Write originalEstimate to Jira. Never raises — returns a result dict."""
    if is_shadow_mode():
        return {"written": False, "reason": "shadow_mode"}
    if not estimated_days or estimated_days <= 0:
        return {"written": False, "reason": "no_estimate"}

    try:
        issue = invoker.get_issue(issue_key)
        existing = (
            ((issue.get("fields") or {}).get("timetracking") or {}).get("originalEstimate") or ""
        )
        if str(existing).strip():
            return {"written": False, "reason": "already_set"}

        estimate = days_to_jira_estimate(float(estimated_days))
        invoker.update_estimate(issue_key, estimate)
        return {"written": True, "estimate": estimate}
    except Exception as exc:
        logger.warning("Jira estimate write failed for %s: %s", issue_key, exc)
        return {"written": False, "reason": str(exc)}
