"""Prompt sections for Jira attachment extracts (Hermes-free)."""

from __future__ import annotations

from typing import Any


def build_attachment_prompt_section(
    attachment_extracts: list[dict[str, Any]] | None,
    *,
    attachments: list[dict[str, Any]] | None = None,
) -> str:
    """Render attachment context for analyst/developer prompts."""
    extracts = [item for item in (attachment_extracts or []) if isinstance(item, dict)]
    metadata = [item for item in (attachments or []) if isinstance(item, dict)]

    if not extracts and not metadata:
        return ""

    lines = [
        "## Jira attachments (mandatory input)",
        "",
        "The ticket includes file attachments. Extracted content below is authoritative "
        "when the description is vague or references screenshots/PJ.",
        "If extraction failed, treat missing visual context as a blocker unless comments "
        "fully specify expected behavior.",
    ]

    if metadata and not extracts:
        lines.extend(["", "### Attachment files"])
        for item in metadata:
            name = str(item.get("name") or item.get("filename") or "attachment")
            mime = str(item.get("mimeType") or item.get("mime_type") or "unknown")
            lines.append(f"- `{name}` ({mime}) — content not extracted")
        return "\n".join(lines)

    lines.append("")
    for index, item in enumerate(extracts, start=1):
        name = str(item.get("name") or "attachment")
        kind = str(item.get("extractKind") or "unknown")
        mime = str(item.get("mimeType") or "")
        lines.append(f"### Attachment {index} — `{name}` ({kind}, {mime or 'unknown type'})")
        content = str(item.get("content") or "").strip()
        error = str(item.get("error") or "").strip()
        if content:
            lines.append(content)
        elif error:
            lines.append(f"(Extraction failed: {error})")
        else:
            lines.append("(No extractable content)")
        lines.append("")

    return "\n".join(lines).rstrip()


def summarize_attachment_extracts(extracts: list[dict[str, Any]] | None) -> str:
    """One-line summary for planning heuristics."""
    items = [item for item in (extracts or []) if isinstance(item, dict)]
    if not items:
        return ""
    usable = [item for item in items if str(item.get("content") or "").strip()]
    if not usable:
        return "Ticket has attachments but automatic extraction did not produce readable content."
    first = str(usable[0].get("content") or "").strip()
    snippet = first[:180].replace("\n", " ")
    suffix = "…" if len(first) > 180 else ""
    return f"Attachment insight: {snippet}{suffix}"
