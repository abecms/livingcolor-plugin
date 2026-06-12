"""Workspace confinement access audit trail (Phase 3G.2)."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from delivery_runtime.shadow.paths import get_evaluation_root

logger = logging.getLogger(__name__)

WORKSPACE_ACCESS_ALLOWED = "WORKSPACE_ACCESS_ALLOWED"
WORKSPACE_ACCESS_BLOCKED = "WORKSPACE_ACCESS_BLOCKED"

WorkspaceAccessTool = Literal["terminal", "file"]


@dataclass(frozen=True)
class WorkspaceAccessEvent:
    event: str
    task_id: str
    path: str
    resolved_path: str
    reason: str
    tool: WorkspaceAccessTool

    def to_dict(self) -> dict[str, str]:
        return {
            "event": self.event,
            "task_id": self.task_id,
            "path": self.path,
            "resolved_path": self.resolved_path,
            "reason": self.reason,
            "tool": self.tool,
        }


@dataclass
class WorkspaceAccessAuditLog:
    events: list[WorkspaceAccessEvent] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, event: WorkspaceAccessEvent) -> None:
        with self._lock:
            self.events.append(event)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event.to_dict(),
        }
        logger.info("%s %s", event.event, json.dumps(payload, sort_keys=True))
        _append_access_file(payload)

    def events_for_task(self, task_id: str) -> list[WorkspaceAccessEvent]:
        with self._lock:
            return [item for item in self.events if item.task_id == task_id]

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "eventCount": len(self.events),
                "events": [item.to_dict() for item in self.events],
            }


_audit_log = WorkspaceAccessAuditLog()
_task_logs: dict[str, list[WorkspaceAccessEvent]] = {}
_task_lock = threading.Lock()


def get_workspace_access_audit_log() -> WorkspaceAccessAuditLog:
    return _audit_log


def reset_workspace_access_audit_log() -> None:
    global _audit_log
    _audit_log = WorkspaceAccessAuditLog()
    with _task_lock:
        _task_logs.clear()


def get_workspace_access_trace(task_id: str) -> list[dict[str, str]]:
    with _task_lock:
        return [item.to_dict() for item in _task_logs.get(task_id, [])]


def clear_workspace_access_trace(task_id: str) -> None:
    with _task_lock:
        _task_logs.pop(task_id, None)


def record_workspace_access(
    *,
    allowed: bool,
    task_id: str,
    path: str,
    resolved_path: str,
    reason: str,
    tool: WorkspaceAccessTool,
) -> WorkspaceAccessEvent:
    event = WorkspaceAccessEvent(
        event=WORKSPACE_ACCESS_ALLOWED if allowed else WORKSPACE_ACCESS_BLOCKED,
        task_id=task_id,
        path=path,
        resolved_path=resolved_path,
        reason=reason,
        tool=tool,
    )
    _audit_log.record(event)
    with _task_lock:
        _task_logs.setdefault(task_id, []).append(event)
    return event


def _append_access_file(payload: dict[str, Any]) -> None:
    root = get_evaluation_root() / "audit"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "workspace-access.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
