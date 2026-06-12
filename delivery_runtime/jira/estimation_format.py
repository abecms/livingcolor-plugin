"""Convert estimated days to Jira time-tracking strings (Hermes-free)."""

from __future__ import annotations

_HOURS_PER_DAY = 8


def days_to_jira_estimate(days: float) -> str:
    """Convert fractional days to a Jira originalEstimate string, e.g. 1.5 -> "1d 4h".

    Uses an 8-hour workday. Rounds up to a minimum of 1 hour.
    """
    if days <= 0:
        raise ValueError("days must be positive")

    total_hours = max(1, round(days * _HOURS_PER_DAY))
    whole_days, hours = divmod(total_hours, _HOURS_PER_DAY)

    parts: list[str] = []
    if whole_days:
        parts.append(f"{whole_days}d")
    if hours:
        parts.append(f"{hours}h")
    return " ".join(parts)
