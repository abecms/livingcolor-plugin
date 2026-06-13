"""Render the external skills context contract for generic role skills."""

from __future__ import annotations

from typing import Any

from delivery_runtime.context.models import ContextPack


def render_skills_context_markdown(pack: ContextPack) -> str:
    ticket = pack.jira_ticket
    architecture = pack.repo_architecture or {}
    stack = architecture.get("stack") or []
    stack_text = ", ".join(str(item) for item in stack) or "Unknown stack"
    summary = str(architecture.get("summary") or "").strip()

    lines = [
        "## Project Stack",
        "",
        f"Stack: {stack_text}",
    ]
    if summary:
        lines.append(f"Summary: {summary}")

    _append_list(lines, "Architecture notes", architecture.get("architectureNotes") or [])
    _append_list(lines, "Repository structure", pack.repo_structure[:20], code=True)
    _append_list(lines, "Project conventions", pack.project_conventions[:8])

    lines.extend(
        [
            "",
            "## Ticket Tracker",
            "",
            "tracker: jira",
            "",
            "## VCS",
            "",
            f"vcs: {pack.vcs_provider or 'gitlab'}",
            "",
            "## Delivery Context",
            "",
            f"Ticket: {pack.jira_key or ticket.get('key') or 'unknown'}",
            f"Summary: {ticket.get('summary') or '(missing)'}",
            f"Issue type: {ticket.get('issueType') or '(missing)'}",
            f"Target repository: {pack.identified_repo or '(unresolved)'}",
        ]
    )
    _append_list(lines, "Acceptance criteria", pack.acceptance_criteria)
    _append_list(lines, "Candidate files", pack.candidate_files[:12], code=True)
    _append_git_history(lines, pack.git_history[:5])
    return "\n".join(lines).strip()


def _append_list(lines: list[str], title: str, values: Any, *, code: bool = False) -> None:
    items = [str(item).strip() for item in values if str(item).strip()] if isinstance(values, list) else []
    if not items:
        return
    lines.extend(["", f"### {title}"])
    for item in items:
        lines.append(f"- `{item}`" if code else f"- {item}")


def _append_git_history(lines: list[str], values: list[dict[str, Any]]) -> None:
    if not values:
        return
    lines.extend(["", "### Relevant git history"])
    for item in values:
        file_path = str(item.get("file") or "").strip()
        sha = str(item.get("sha") or "")[:8]
        message = str(item.get("message") or "").strip()
        if file_path:
            lines.append(f"- `{file_path}` - {sha} {message}".strip())
