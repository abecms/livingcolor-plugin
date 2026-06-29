"""Hermes-free prompt assembly and completion parsing for Gate 1 implementation planning."""

from __future__ import annotations

import json
import re
from typing import Any

from delivery_runtime.context.models import ContextPack
from delivery_runtime.context.planner import validate_plan_payload
from delivery_runtime.context.repo_architecture import format_architecture_for_prompt
from delivery_runtime.readiness.attachment_prompt import build_attachment_prompt_section

WILDCARD_PATTERN = re.compile(r"\*\*?$|/\*\*")


class PlannerParseError(ValueError):
    """Raised when a planner agent completion cannot be parsed into Gate 1 JSON."""


def build_planner_user_prompt(pack: ContextPack) -> str:
    """Build the user message for an implementation planning turn."""
    ticket = pack.jira_ticket
    title = str(ticket.get("summary") or "").strip()
    description = str(ticket.get("description") or "").strip()
    issue_type = str(ticket.get("issueType") or "").strip()
    project_key = str(ticket.get("projectKey") or "").strip()

    sections = [
        "# LivingColor Planner Agent — Gate 1 implementation plan",
        "",
        "Produce an implementation plan for autonomous developer handoff at Gate 1.",
        "This is read-only planning — never edit files, push commits, or mutate Jira.",
        "",
        f"Jira key: {pack.jira_key or 'unknown'}",
        f"Project key: {project_key or 'unknown'}",
        "",
        "## Ticket",
        f"- Title: {title or '(missing)'}",
        f"- Issue type: {issue_type or '(missing)'}",
        "",
        "### Description",
        description or "(missing)",
        "",
        "## Acceptance criteria",
    ]

    if pack.acceptance_criteria:
        for index, criterion in enumerate(pack.acceptance_criteria, start=1):
            sections.append(f"{index}. {criterion}")
    else:
        sections.append("(none extracted — infer from title, description, and attachments)")

    if pack.jira_comments:
        sections.extend(["", "## Jira comments (mandatory input)", ""])
        for index, comment in enumerate(pack.jira_comments, start=1):
            author = comment.get("author") or "unknown"
            created = comment.get("created") or "unknown time"
            sections.append(f"### Comment {index} — {author} ({created})")
            sections.append(str(comment.get("body") or "").strip())
            sections.append("")

    attachment_section = build_attachment_prompt_section(
        pack.jira_attachment_extracts,
        attachments=ticket.get("attachments") if isinstance(ticket.get("attachments"), list) else None,
    )
    if attachment_section:
        sections.extend(["", attachment_section])

    if pack.epic:
        sections.extend(
            [
                "",
                "## Epic context",
                f"- Key: {(pack.epic or {}).get('key')}",
                f"- Summary: {(pack.epic or {}).get('summary') or '(missing)'}",
            ]
        )

    if pack.linked_tickets:
        sections.extend(["", "## Linked tickets"])
        for item in pack.linked_tickets[:5]:
            sections.append(f"- {item.get('key')}: {item.get('summary') or '(no summary)'}")

    if pack.rejection_feedback:
        sections.extend(
            [
                "",
                "## Reviewer feedback (must address in replan)",
                pack.rejection_feedback.strip(),
            ]
        )

    sections.extend(
        [
            "",
            "## Repository context",
            f"- Identified repo: {pack.identified_repo or '(unresolved)'}",
            f"- Local checkout: {pack.repo_checkout_path or '(none — rely on structure hints below)'}",
        ]
    )

    architecture_brief = format_architecture_for_prompt(pack.repo_architecture)
    if architecture_brief:
        sections.extend(["", "### Repository architecture", architecture_brief])

    if pack.skills_context_markdown:
        sections.extend(
            [
                "",
                "## External skills context",
                "Use this context when applying generic LivingColor role skills.",
                "",
                pack.skills_context_markdown,
            ]
        )

    if pack.project_conventions:
        sections.extend(["", "## Project conventions"])
        sections.extend(f"- {item}" for item in pack.project_conventions[:8])

    if pack.candidate_files:
        sections.extend(
            [
                "",
                "## Heuristic candidate files (verify — may be wrong)",
                "These paths were scored by keyword overlap only. False positives happen when",
                "French/English tokens match unrelated English path segments (e.g. est→tests,",
                "dire→direct). **Do not pick the top candidate blindly.** Derive impacted files",
                "from the ticket title, description, URLs, and attachment content first.",
            ]
        )
        for path in pack.candidate_files[:12]:
            sections.append(f"- `{path}`")

    if pack.repo_structure:
        sections.extend(
            [
                "",
                "## Repository structure sample",
                "Use this to locate real modules when candidates look wrong.",
            ]
        )
        for path in pack.repo_structure[:40]:
            sections.append(f"- `{path}`")

    if pack.git_history:
        sections.extend(["", "## Recent git history on candidate paths"])
        for item in pack.git_history[:5]:
            sections.append(
                f"- `{item.get('file')}` — {item.get('sha', '')[:8]} {item.get('message', '')[:80]}"
            )

    if pack.build_notes:
        sections.extend(["", "## Build notes"])
        sections.extend(f"- {note}" for note in pack.build_notes)

    context_pack_reference = pack.to_dict()
    if pack.skills_context_markdown:
        context_pack_reference["skills_context_markdown"] = "(see External skills context section above)"

    sections.extend(
        [
            "",
            "## Planning rules",
            "- Resolve the **actual** feature area from ticket text and attachments before choosing files.",
            "- For SEO/rendering/crawlability issues, prioritize templates, controllers, and page entry",
            "  assets over unrelated unit tests unless tests are explicitly in scope.",
            "- When a local checkout path is available, use read-only file tools to confirm paths exist.",
            "- If the repository cannot be identified or scope is ambiguous, set needsClarification true.",
            "- Never emit wildcard paths (e.g. src/**) or targetRepo='unknown'.",
            "",
            "Finish with a JSON completion block matching this schema:",
            "",
            "```json",
            "{",
            '  "needsClarification": false,',
            '  "clarificationReason": "",',
            '  "ticketUnderstanding": "...",',
            '  "targetRepo": "group/project",',
            '  "implementationPlan": "numbered steps as plain text",',
            '  "likelyImpactedFiles": ["path/one", "path/two"],',
            '  "risks": ["risk one"],',
            '  "confidenceLevel": 0.85',
            "}",
            "```",
            "",
            "### Context pack JSON (reference)",
            json.dumps(context_pack_reference, indent=2, sort_keys=True),
        ]
    )
    return "\n".join(sections)


def parse_planner_completion(text: str, pack: ContextPack) -> dict[str, Any]:
    """Extract Gate 1 plan JSON from a planner agent completion."""
    payload = _extract_json_object(text)
    if payload is None:
        raise PlannerParseError("planner completion is missing a JSON block")

    needs_clarification = bool(payload.get("needsClarification"))
    if needs_clarification:
        reason = str(payload.get("clarificationReason") or "").strip()
        if not reason:
            raise PlannerParseError("needsClarification=true requires clarificationReason")
        return {
            "needsClarification": True,
            "clarificationReason": reason,
            "contextPack": pack.to_dict(),
        }

    missing = [
        field
        for field in (
            "ticketUnderstanding",
            "targetRepo",
            "implementationPlan",
            "likelyImpactedFiles",
            "risks",
            "confidenceLevel",
        )
        if field not in payload
    ]
    if missing:
        raise PlannerParseError(f"planner completion is missing required fields: {', '.join(missing)}")

    impacted = payload["likelyImpactedFiles"]
    if not isinstance(impacted, list) or not impacted:
        impacted_paths = [str(item).strip() for item in (pack.candidate_files or []) if str(item).strip()]
        if not impacted_paths:
            raise PlannerParseError("likelyImpactedFiles must be a non-empty list")
    else:
        impacted_paths = [str(item).strip() for item in impacted if str(item).strip()]
        if not impacted_paths and pack.candidate_files:
            impacted_paths = [str(item).strip() for item in pack.candidate_files if str(item).strip()]
        if not impacted_paths:
            raise PlannerParseError("likelyImpactedFiles must contain at least one path")

    risks = payload["risks"]
    if not isinstance(risks, list):
        raise PlannerParseError("risks must be a list")

    confidence = payload["confidenceLevel"]
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise PlannerParseError("confidenceLevel must be numeric")

    for path in impacted_paths:
        if WILDCARD_PATTERN.search(path):
            raise PlannerParseError(f"planner must not emit wildcard paths: {path}")

    result = {
        "needsClarification": False,
        "ticketUnderstanding": str(payload["ticketUnderstanding"] or "").strip(),
        "jiraContextUsed": {
            **pack.jira_ticket,
            "acceptanceCriteria": pack.acceptance_criteria,
            "commentCount": len(pack.jira_comments),
            "linkedTicketCount": len(pack.linked_tickets),
            "epicKey": (pack.epic or {}).get("key"),
        },
        "targetRepo": str(payload["targetRepo"] or "").strip(),
        "implementationPlan": str(payload["implementationPlan"] or "").strip(),
        "likelyImpactedFiles": impacted_paths[:5],
        "risks": [str(item) for item in risks][:5],
        "confidenceLevel": round(float(confidence), 2),
        "contextPack": pack.to_dict(),
    }
    validate_plan_payload(result)
    return result


def _extract_json_object(text: str) -> dict[str, Any] | None:
    payload = text or ""
    start = payload.rfind("```json")
    if start != -1:
        block = payload[start + len("```json") :]
        end = block.find("```")
        if end != -1:
            payload = block[:end].strip()
        else:
            payload = block.strip()
    else:
        payload = payload.strip()

    if not payload:
        return None

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        brace_start = (text or "").rfind("{")
        brace_end = (text or "").rfind("}")
        if brace_start == -1 or brace_end <= brace_start:
            return None
        try:
            parsed = json.loads(text[brace_start : brace_end + 1])
        except json.JSONDecodeError:
            return None

    return parsed if isinstance(parsed, dict) else None
