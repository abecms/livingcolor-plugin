"""Automatic and manual LivingColor sprint reset."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.persistence.db import utc_now_iso
from delivery_runtime.pm_inbox import store as pm_store
from delivery_runtime.pm_inbox.sprint_selection import (
    build_selected_sprint_payload,
    merge_active_work_orders_into_sprint,
    persist_selected_sprint,
)


def _today(now: datetime) -> date:
    return now.astimezone(UTC).date()


def _today_iso(now: datetime) -> str:
    return _today(now).isoformat()


def _parse_start_date(raw: str) -> date | None:
    value = raw.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _current_sprint_number(project_key: str) -> int:
    state = pm_store.get_sprint_state(project_key=project_key)
    memory = (state or {}).get("memory") or {}
    if not isinstance(memory, dict):
        return 0
    try:
        return max(0, int(memory.get("sprintNumber") or 0))
    except (TypeError, ValueError):
        return 0


def _last_sprint_start_date(memory: dict[str, Any]) -> date | None:
    for key in ("sprintStartDate", "lastResetDate"):
        parsed = _parse_start_date(str(memory.get(key) or ""))
        if parsed is not None:
            return parsed
    return None


def sprint_end_date(*, start: date, duration_days: int) -> date:
    """Return the last calendar day of a sprint that spans `duration_days` from `start`."""
    return start + timedelta(days=max(1, duration_days) - 1)


def should_auto_reset_sprint(*, project_key: str, now: datetime | None = None) -> bool:
    """Start a new sprint on the configured weekday once the previous sprint duration elapsed."""
    project_key = project_key.strip().upper()
    config = load_delivery_automation_config(project_key=project_key)
    start_weekday = config.sprint.start_weekday
    duration_days = max(1, config.sprint.duration_days)
    now = now or datetime.now(UTC)
    today = _today(now)
    if today.isoweekday() != start_weekday:
        return False

    state = pm_store.get_sprint_state(project_key=project_key)
    memory = (state or {}).get("memory") or {}
    if not isinstance(memory, dict):
        return True

    last_start = _last_sprint_start_date(memory)
    if last_start is None:
        return True
    return (today - last_start).days >= duration_days


def reset_sprint(
    *,
    project_key: str,
    now: datetime | None = None,
    repopulate_tickets: bool = True,
    publish_report: bool = True,
) -> dict[str, Any]:
    """Clear manual override, bump sprint number, and optionally rebuild ticket selection."""
    project_key = project_key.strip().upper()
    now = now or datetime.now(UTC)

    if publish_report:
        from delivery_runtime.pm_inbox.sprint_report import maybe_publish_sprint_report_before_reset

        maybe_publish_sprint_report_before_reset(project_key=project_key, now=now)

    today = _today(now)
    config = load_delivery_automation_config(project_key=project_key)
    duration_days = max(1, config.sprint.duration_days)
    sprint_number = _current_sprint_number(project_key) + 1
    end = sprint_end_date(start=today, duration_days=duration_days)

    if repopulate_tickets:
        payload = build_selected_sprint_payload(
            project_key=project_key,
            sprint_number=sprint_number,
        )
        payload = merge_active_work_orders_into_sprint(payload, project_key=project_key)
    else:
        sprint_name = f"LivingColor Sprint {sprint_number}" if sprint_number else "LivingColor Sprint"
        payload = {
            "sprintName": sprint_name,
            "capacityDays": config.sprint.capacity_days,
            "usedDays": 0.0,
            "durationDays": duration_days,
            "overflowRisk": False,
            "warnings": [],
            "tickets": [],
        }

    persist_selected_sprint(
        project_key=project_key,
        payload=payload,
        memory_patch={
            "manualOverride": False,
            "manualOverrideAt": None,
            "emptyBacklogUntilAnalysis": not repopulate_tickets,
            "sprintNumber": sprint_number,
            "sprintStartDate": today.isoformat(),
            "sprintEndDate": end.isoformat(),
            "lastResetDate": today.isoformat(),
            "lastResetAt": utc_now_iso(),
        },
    )
    return payload


def maybe_auto_reset_sprint(*, project_key: str, now: datetime | None = None) -> dict[str, Any] | None:
    if should_auto_reset_sprint(project_key=project_key, now=now):
        return reset_sprint(project_key=project_key, now=now)
    return None
