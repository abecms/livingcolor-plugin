"""Context Pack data model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ContextPack:
    """Structured context assembled before any implementation planning."""

    jira_key: str
    jira_ticket: dict[str, Any]
    jira_comments: list[dict[str, Any]] = field(default_factory=list)
    jira_attachment_extracts: list[dict[str, Any]] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    epic: dict[str, Any] | None = None
    linked_tickets: list[dict[str, Any]] = field(default_factory=list)
    identified_repo: str | None = None
    repo_checkout_path: str | None = None
    repo_structure: list[str] = field(default_factory=list)
    candidate_files: list[str] = field(default_factory=list)
    project_conventions: list[str] = field(default_factory=list)
    git_history: list[dict[str, Any]] = field(default_factory=list)
    repo_architecture: dict[str, Any] = field(default_factory=dict)
    rejection_feedback: str = ""
    resolved_repo_override: str | None = None
    build_notes: list[str] = field(default_factory=list)

    @property
    def repo_resolved(self) -> bool:
        return bool(self.identified_repo)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
