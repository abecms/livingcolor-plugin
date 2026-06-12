"""Hermes-free prompt assembly and completion parsing for analyst readiness runs."""

from __future__ import annotations

import json
from typing import Any

from delivery_runtime.readiness.attachment_prompt import build_attachment_prompt_section


class AnalystParseError(ValueError):
    """Raised when an analyst agent completion cannot be parsed into readiness JSON."""


_REQUIRED_FIELDS = (
    "readinessScore",
    "readinessStatus",
    "analysisSummary",
    "blockers",
    "recommendedRepos",
    "confidence",
)


def build_analyst_user_prompt(snapshot: dict[str, Any]) -> str:
    """Build the user message for a readiness analysis turn."""
    jira_key = str(snapshot.get("key") or "").strip()
    project_key = str(snapshot.get("projectKey") or "").strip()
    title = str(snapshot.get("summary") or snapshot.get("title") or "").strip()
    description = str(snapshot.get("description") or "").strip()
    issue_type = str(snapshot.get("issueType") or snapshot.get("issue_type") or "").strip()
    status = str(snapshot.get("status") or "").strip()
    comments = _normalize_prompt_comments(snapshot.get("comments"))
    reanalyze = bool(snapshot.get("reanalyzeContext"))
    is_reopened = bool(snapshot.get("isReopened")) or _looks_reopened(status, comments)

    sections = [
        "# LivingColor Analyst Agent",
        "",
        "Analyze the Jira ticket snapshot below for autonomous delivery readiness.",
        "This is read-only analysis — never mutate Jira, create Work Orders, or promote tickets.",
        "",
        f"Jira key: {jira_key or 'unknown'}",
        f"Project key: {project_key or 'unknown'}",
        "",
        "## Ticket snapshot",
        f"- Title: {title or '(missing)'}",
        f"- Issue type: {issue_type or '(missing)'}",
        f"- Status: {status or '(missing)'}",
        "",
        "### Description",
        description or "(missing)",
        "",
        _build_comments_section(comments, reanalyze=reanalyze, is_reopened=is_reopened),
    ]
    attachment_section = build_attachment_prompt_section(
        snapshot.get("attachmentExtracts"),
        attachments=snapshot.get("attachments"),
    )
    if attachment_section:
        sections.extend(["", attachment_section])
    sections.extend(
        [
            "",
            "### Raw snapshot JSON",
            json.dumps(snapshot, indent=2, sort_keys=True),
            "",
            "Apply the readiness scoring rubric and finish with a JSON completion block matching",
            "the analyze_ticket_snapshot schema (readinessScore, readinessStatus, analysisSummary,",
            "blockers, recommendedRepos, confidence, estimatedDays).",
            "estimatedDays is your effort estimate in workdays (8h) as a number, e.g. 1.5.",
        ]
    )
    return "\n".join(sections)


def _normalize_prompt_comments(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    comments: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        body = str(item.get("body") or item.get("text") or "").strip()
        if not body:
            continue
        comments.append(
            {
                "author": str(item.get("author") or "").strip() or None,
                "body": body,
                "created": str(item.get("created") or "").strip() or None,
            }
        )
    return comments


def _looks_reopened(status: str, comments: list[dict[str, Any]]) -> bool:
    lowered_status = status.lower()
    if "reopen" in lowered_status:
        return True
    for comment in comments:
        body = str(comment.get("body") or "").lower()
        if any(token in body for token in ("reopened", "re-opened", "re open", "back to dev", "sent back")):
            return True
    return False


def _build_comments_section(
    comments: list[dict[str, Any]],
    *,
    reanalyze: bool,
    is_reopened: bool,
) -> str:
    lines = [
        "## Jira comments (mandatory input)",
        "",
        "You MUST read every comment below. Comments often contain QA feedback, scope changes,",
        "blockers, acceptance-criteria clarifications, and rejection reasons that are not in the",
        "original description.",
    ]
    if reanalyze or is_reopened:
        lines.extend(
            [
                "",
                "### Re-opened / re-analysis context",
                "This ticket is being re-analyzed" + (" after reopening" if is_reopened else "") + ".",
                "Treat Jira comments as the source of truth over the original description.",
                "If comments explain why the ticket was rejected or sent back, reflect that in",
                "blockers, readinessScore, and analysisSummary. Do not mark ready while open",
                "feedback in comments remains unresolved.",
            ]
        )
    if not comments:
        lines.extend(
            [
                "",
                "No Jira comments were captured in this snapshot.",
            ]
        )
        if reanalyze or is_reopened:
            lines.append(
                "For reopened tickets, missing comment context is a blocker — prefer not_ready."
            )
        return "\n".join(lines)

    lines.append("")
    for index, comment in enumerate(comments, start=1):
        author = comment.get("author") or "unknown"
        created = comment.get("created") or "unknown time"
        lines.append(f"### Comment {index} — {author} ({created})")
        lines.append(str(comment.get("body") or "").strip())
        lines.append("")
    return "\n".join(lines).rstrip()


def parse_analyst_completion(text: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Extract readiness analysis JSON from an analyst agent completion."""
    payload = _extract_json_object(text)
    if payload is None:
        raise AnalystParseError("analyst completion is missing a JSON block")

    missing = [field for field in _REQUIRED_FIELDS if field not in payload]
    if missing:
        raise AnalystParseError(f"analyst completion is missing required fields: {', '.join(missing)}")

    readiness_score = payload["readinessScore"]
    if not isinstance(readiness_score, (int, float)):
        raise AnalystParseError("readinessScore must be numeric")
    readiness_status = str(payload["readinessStatus"] or "").strip()
    if readiness_status not in {"ready", "not_ready"}:
        raise AnalystParseError("readinessStatus must be 'ready' or 'not_ready'")

    blockers = payload["blockers"]
    if not isinstance(blockers, list):
        raise AnalystParseError("blockers must be a list")
    recommended_repos = payload["recommendedRepos"]
    if not isinstance(recommended_repos, list):
        raise AnalystParseError("recommendedRepos must be a list")

    confidence = payload["confidence"]
    if not isinstance(confidence, (int, float)):
        raise AnalystParseError("confidence must be numeric")

    estimated_days = payload.get("estimatedDays")
    if not isinstance(estimated_days, (int, float)) or isinstance(estimated_days, bool) or estimated_days <= 0:
        estimated_days = None

    return {
        "readinessScore": int(readiness_score),
        "readinessStatus": readiness_status,
        "analysisSummary": str(payload["analysisSummary"] or "").strip(),
        "blockers": [str(item) for item in blockers],
        "recommendedRepos": [str(item) for item in recommended_repos if str(item).strip()],
        "confidence": float(confidence),
        "estimatedDays": float(estimated_days) if estimated_days else None,
        "jiraSnapshot": snapshot,
    }


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
            parsed = json.loads((text or "")[brace_start : brace_end + 1])
        except json.JSONDecodeError:
            return None

    return parsed if isinstance(parsed, dict) else None
