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
    "estimatedDays",
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
            "## LivingColor readiness semantics",
            "",
            "- ready: implementation can start from the ticket and available repo context.",
            "- not_ready: ticket is blocked by missing technical information, dependency, environment, or contradiction.",
            "- needs_clarification: genuine product/UX/business ambiguity that must be resolved before implementation.",
            "- not_development: request is not implementation work.",
            "- analysis_failed: reserved for runtime failures; do not emit it as a normal LLM classification.",
            "",
            "Technical tickets can be ready when they include enough operational detail, even when they are",
            "not written as user stories or formal Gherkin acceptance criteria.",
            "SEO JSON-LD, schema.org, dataLayer, Airship tracking, BFF behavior, frontend UI,",
            "backend behavior, and playback/access bugs are development work unless the ticket explicitly says otherwise.",
            "Prefer ready when the title, description, target behavior, and repo context are sufficient and",
            "no unresolved comment blocks implementation.",
            "",
            "## Response contract",
            "",
            "Return strict JSON, either fenced as ```json or as a raw parseable JSON object.",
            "Use exactly these fields: readinessScore, readinessStatus, analysisSummary, blockers,",
            "recommendedRepos, confidence, estimatedDays.",
            "readinessStatus must be one of: ready, not_ready, needs_clarification, not_development.",
            "Do not use analysis_failed; it is only for runtime/parser failures outside this analysis.",
            "blockers and recommendedRepos must be arrays. estimatedDays is your effort estimate in",
            "workdays (8h) as a number, e.g. 1.5.",
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


def parse_analyst_completion(
    text: str,
    snapshot: dict[str, Any],
    *,
    allow_runtime_statuses: bool = False,
) -> dict[str, Any]:
    """Extract readiness analysis JSON from an analyst agent completion."""
    payload = _extract_json_object(text)
    if payload is None:
        raise AnalystParseError("analyst completion is missing a JSON block")

    missing = [field for field in _REQUIRED_FIELDS if field not in payload]
    if missing:
        raise AnalystParseError(f"analyst completion is missing required fields: {', '.join(missing)}")

    readiness_score = payload["readinessScore"]
    if not isinstance(readiness_score, (int, float)) or isinstance(readiness_score, bool):
        raise AnalystParseError("readinessScore must be numeric")
    readiness_status = _normalize_analyst_readiness_status(
        str(payload["readinessStatus"] or ""),
        allow_runtime_statuses=allow_runtime_statuses,
    )
    if readiness_status is None:
        allowed_statuses = "ready, not_ready, needs_clarification, not_development"
        if allow_runtime_statuses:
            allowed_statuses += ", analysis_failed"
        raise AnalystParseError(
            f"readinessStatus must be one of: {allowed_statuses}"
        )

    analysis_summary = payload["analysisSummary"]
    if not isinstance(analysis_summary, str):
        raise AnalystParseError("analysisSummary must be a string")

    blockers = payload["blockers"]
    if not isinstance(blockers, list):
        raise AnalystParseError("blockers must be a list")
    recommended_repos = payload["recommendedRepos"]
    if not isinstance(recommended_repos, list):
        raise AnalystParseError("recommendedRepos must be a list")

    confidence = payload["confidence"]
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise AnalystParseError("confidence must be numeric")

    estimated_days = payload.get("estimatedDays")
    if not isinstance(estimated_days, (int, float)) or isinstance(estimated_days, bool) or estimated_days <= 0:
        raise AnalystParseError("estimatedDays must be a positive number")

    return {
        "readinessScore": int(readiness_score),
        "readinessStatus": readiness_status,
        "analysisSummary": analysis_summary.strip(),
        "blockers": [str(item) for item in blockers],
        "recommendedRepos": [str(item) for item in recommended_repos if str(item).strip()],
        "confidence": float(confidence),
        "estimatedDays": float(estimated_days),
        "jiraSnapshot": snapshot,
    }


def _normalize_analyst_readiness_status(raw: str, *, allow_runtime_statuses: bool = False) -> str | None:
    normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "notready": "not_ready",
        "needsclarification": "needs_clarification",
        "notdevelopment": "not_development",
        "analysisfailed": "analysis_failed",
    }
    normalized = aliases.get(normalized, normalized)
    allowed = {"ready", "not_ready", "needs_clarification", "not_development"}
    if allow_runtime_statuses:
        allowed.add("analysis_failed")
    if normalized in allowed:
        return normalized
    return None


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
        return None

    return parsed if isinstance(parsed, dict) else None
