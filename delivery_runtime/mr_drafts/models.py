"""Merge Request Draft domain model (Phase 4A — internal artifact, not GitLab)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

MrDraftStatus = Literal["draft", "awaiting_review", "approved", "rejected"]


@dataclass(frozen=True)
class MergeRequestDraft:
    id: str
    work_order_id: str
    title: str
    description: str
    ticket_summary: str
    implementation_summary: str
    files_modified: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    reviewers: list[str] = field(default_factory=list)
    qa_checklist: dict[str, Any] = field(default_factory=dict)
    decision_trace: dict[str, Any] = field(default_factory=dict)
    mr_url: str = ""
    mr_iid: int | None = None
    status: MrDraftStatus = "awaiting_review"
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workOrderId": self.work_order_id,
            "title": self.title,
            "description": self.description,
            "ticketSummary": self.ticket_summary,
            "implementationSummary": self.implementation_summary,
            "filesModified": self.files_modified,
            "risks": self.risks,
            "reviewers": self.reviewers,
            "qaChecklist": self.qa_checklist,
            "decisionTrace": self.decision_trace,
            "mrUrl": self.mr_url,
            "mrIid": self.mr_iid,
            "status": self.status,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MergeRequestDraft:
        return cls(
            id=str(payload.get("id") or ""),
            work_order_id=str(payload.get("workOrderId") or ""),
            title=str(payload.get("title") or ""),
            description=str(payload.get("description") or ""),
            ticket_summary=str(payload.get("ticketSummary") or ""),
            implementation_summary=str(payload.get("implementationSummary") or ""),
            files_modified=[str(item) for item in payload.get("filesModified") or []],
            risks=[str(item) for item in payload.get("risks") or []],
            reviewers=[str(item) for item in payload.get("reviewers") or []],
            qa_checklist=dict(payload.get("qaChecklist") or {}),
            decision_trace=dict(payload.get("decisionTrace") or {}),
            mr_url=str(payload.get("mrUrl") or ""),
            mr_iid=int(payload["mrIid"]) if payload.get("mrIid") is not None else None,
            status=str(payload.get("status") or "awaiting_review"),  # type: ignore[arg-type]
            created_at=str(payload.get("createdAt") or ""),
            updated_at=str(payload.get("updatedAt") or ""),
        )
