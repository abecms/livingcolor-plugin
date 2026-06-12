"""Delivery analyst for daily BN pipeline."""

from __future__ import annotations

from typing import Any

from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.communication.language import (
    get_clarification_comment_template,
    get_not_development_comment_template,
)
from delivery_runtime.readiness.analyzer import analyze_ticket_snapshot
from delivery_runtime.readiness.scoring import score_ticket
from delivery_runtime.readiness.project_mapping import resolve_recommended_repos

NOT_DEVELOPMENT_ISSUE_TYPES = {
    "request",
    "question",
    "support",
    "incident",
    "service request",
    "change",
    "improvement request",
}

NOT_DEVELOPMENT_KEYWORDS = (
    "content update",
    "editorial",
    "copy change",
    "wording",
    "support request",
    "business question",
    "faq",
    "documentation only",
    "translate",
    "translation",
)

from delivery_runtime.readiness.ticket_quality import (
    has_acceptance_criteria,
    has_actionable_specification,
    has_impacted_url,
    has_reproduction_steps,
    is_infrastructure_blocker,
)


def _combined_text(snapshot: dict[str, Any]) -> str:
    parts = [
        str(snapshot.get("summary") or snapshot.get("title") or ""),
        str(snapshot.get("description") or ""),
        str(snapshot.get("issueType") or snapshot.get("issue_type") or ""),
    ]
    return " ".join(parts).lower()


def _is_not_development(snapshot: dict[str, Any]) -> tuple[bool, str]:
    issue_type = str(snapshot.get("issueType") or snapshot.get("issue_type") or "").strip().lower()
    text = _combined_text(snapshot)

    if issue_type in NOT_DEVELOPMENT_ISSUE_TYPES:
        return True, f"Issue type '{issue_type}' is not a development delivery item"

    for keyword in NOT_DEVELOPMENT_KEYWORDS:
        if keyword in text:
            return True, f"Ticket content suggests a non-development request ({keyword})"

    labels = snapshot.get("labels") or []
    label_text = " ".join(str(item).lower() for item in labels)
    if "non-dev" in label_text or "non_dev" in label_text or "content" in label_text:
        return True, "Ticket labels indicate a non-development request"

    return False, ""


def _specification_blockers(blockers: list[str]) -> list[str]:
    return [item for item in blockers if not is_infrastructure_blocker(item)]


def _missing_information(snapshot: dict[str, Any], blockers: list[str]) -> tuple[bool, list[str]]:
    description = str(snapshot.get("description") or "").strip()
    summary = str(snapshot.get("summary") or snapshot.get("title") or "").strip()
    issues: list[str] = []

    issue_type = str(snapshot.get("issueType") or snapshot.get("issue_type") or "").lower()
    actionable_spec = has_actionable_specification(
        description,
        issue_type=issue_type,
        summary=summary,
    )

    if len(description) < 40:
        issues.append("Description is too short or missing context")

    if issue_type == "bug" and not has_reproduction_steps(description) and not actionable_spec:
        issues.append("Reproduction steps are missing")

    if (
        not has_impacted_url(description)
        and issue_type in {"bug", "story", "task"}
        and not actionable_spec
    ):
        issues.append("Impacted page URL was not found")

    if not has_acceptance_criteria(description, issue_type=issue_type, summary=summary):
        acceptance_blockers = [item for item in blockers if "acceptance criteria" in item.lower()]
        if acceptance_blockers:
            issues.append(acceptance_blockers[0])

    if not issues:
        issues.extend(_specification_blockers(blockers)[:2])

    return bool(issues), issues


def analyze_for_daily_delivery(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Extended analyst used by the daily pipeline (does not publish to Jira)."""
    language = load_delivery_automation_config().communication_language
    clarification_template = get_clarification_comment_template(language)
    not_development_template = get_not_development_comment_template(language)
    base = analyze_ticket_snapshot(snapshot)
    project_key = str(snapshot.get("projectKey") or base["jiraSnapshot"].get("projectKey") or "").strip()
    if not project_key:
        key = str(snapshot.get("key") or "")
        project_key = key.split("-")[0] if "-" in key else ""

    repos = resolve_recommended_repos(project_key, snapshot)
    score_result = score_ticket(snapshot, recommended_repos=repos)

    not_dev, not_dev_reason = _is_not_development(snapshot)
    if not_dev:
        return {
            **base,
            "readinessStatus": "not_development",
            "analysisSummary": (
                f"{snapshot.get('key', 'Ticket')} is classified as not a development ticket. {not_dev_reason}."
            ),
            "blockers": [not_dev_reason],
            "analystCategory": "not_development",
            "detectedIssues": [not_dev_reason],
            "proposedComment": not_development_template,
            "proposalType": "not_development",
            "actionable": False,
        }

    missing, detected_issues = _missing_information(snapshot, score_result.blockers)
    spec_blockers = _specification_blockers(score_result.blockers)
    needs_clarification = bool(detected_issues) or (
        score_result.score < 70 and bool(spec_blockers)
    )

    if needs_clarification:
        return {
            **base,
            "readinessScore": score_result.score,
            "readinessStatus": "needs_clarification",
            "analysisSummary": (
                f"{snapshot.get('key', 'Ticket')} needs clarification before delivery "
                f"({score_result.score}/100)."
            ),
            "blockers": detected_issues or spec_blockers,
            "analystCategory": "needs_clarification",
            "detectedIssues": detected_issues or spec_blockers,
            "proposedComment": clarification_template,
            "proposalType": "needs_clarification",
            "actionable": False,
        }

    infrastructure_blockers = [
        item for item in score_result.blockers if is_infrastructure_blocker(item)
    ]
    if infrastructure_blockers:
        return {
            **base,
            "readinessScore": score_result.score,
            "readinessStatus": "ready",
            "analysisSummary": (
                f"{snapshot.get('key', 'Ticket')} is specification-ready ({score_result.score}/100) "
                f"but requires project repository mapping before execution."
            ),
            "blockers": infrastructure_blockers,
            "analystCategory": "needs_repo_mapping",
            "detectedIssues": infrastructure_blockers,
            "proposedComment": "",
            "proposalType": "",
            "actionable": True,
        }

    return {
        **base,
        "readinessScore": score_result.score,
        "readinessStatus": "ready",
        "analysisSummary": base["analysisSummary"],
        "blockers": [],
        "analystCategory": "development_ready",
        "detectedIssues": [],
        "proposedComment": "",
        "proposalType": "",
        "actionable": True,
    }
