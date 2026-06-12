"""Deterministic Merge Request Draft generator (Phase 4A)."""

from __future__ import annotations

from typing import Any

from delivery_runtime.explainability import build_decision_trace
from delivery_runtime.communication.language import get_mr_labels


def generate_mr_draft_content(
    *,
    jira_key: str,
    work_order_title: str,
    jira_snapshot: dict[str, Any],
    approved_plan: dict[str, Any],
    context_pack: dict[str, Any],
    code_review_payload: dict[str, Any],
    scope_validation: dict[str, Any] | None = None,
    scope_contract: dict[str, Any] | None = None,
    communication_language: str | None = None,
) -> dict[str, Any]:
    """Build MR draft fields from recorded delivery evidence only."""
    labels = get_mr_labels(communication_language)
    scope_validation = scope_validation or code_review_payload.get("scopeValidation") or {}
    summary = str(jira_snapshot.get("summary") or work_order_title or jira_key).strip()
    description = str(jira_snapshot.get("description") or "").strip()
    acceptance = _extract_acceptance_criteria(description, labels)
    ticket_summary = _build_ticket_summary(jira_key, summary, description, acceptance, labels)

    implementation_plan = str(approved_plan.get("implementationPlan") or "").strip()
    dev_summary = str(code_review_payload.get("summary") or "").strip()
    implementation_summary = dev_summary or implementation_plan or labels["noImplementationSummary"]

    files_modified = _unique_paths(
        list(code_review_payload.get("filesModified") or [])
        + list(code_review_payload.get("filesCreated") or [])
    )
    if not files_modified:
        files_modified = _unique_paths(list(approved_plan.get("likelyImpactedFiles") or []))

    risks = _collect_risks(approved_plan, code_review_payload, scope_validation)
    reviewers = _derive_reviewers(context_pack, approved_plan, labels)
    qa_checklist = _build_qa_checklist(code_review_payload, scope_validation)
    decision_trace = build_decision_trace(
        jira_key=jira_key,
        jira_snapshot=jira_snapshot,
        approved_plan=approved_plan,
        context_pack=context_pack,
        code_review_payload=code_review_payload,
        files_modified=files_modified,
        scope_validation=scope_validation,
        scope_contract=scope_contract,
    )
    structured_risks = decision_trace.risk_assessment.summary or risks

    title = f"{jira_key} {summary}".strip()
    markdown_description = _build_description_markdown(
        ticket_summary=ticket_summary,
        implementation_summary=implementation_summary,
        files_modified=files_modified,
        risks=structured_risks,
        qa_checklist=qa_checklist,
        reviewers=reviewers,
        decision_trace=decision_trace.to_dict(),
        labels=labels,
    )

    return {
        "title": title,
        "description": markdown_description,
        "ticketSummary": ticket_summary,
        "implementationSummary": implementation_summary,
        "filesModified": files_modified,
        "risks": structured_risks,
        "reviewers": reviewers,
        "qaChecklist": qa_checklist,
        "decisionTrace": decision_trace.to_dict(),
    }


def _build_ticket_summary(
    jira_key: str,
    summary: str,
    description: str,
    acceptance: str,
    labels: dict[str, str],
) -> str:
    lines = [f"{jira_key}: {summary}" if summary else jira_key]
    if description:
        lines.append("")
        lines.append(description)
    if acceptance:
        lines.append("")
        lines.append(f"{labels['acceptanceCriteria']}: {acceptance}")
    return "\n".join(lines).strip()


def _build_description_markdown(
    *,
    ticket_summary: str,
    implementation_summary: str,
    files_modified: list[str],
    risks: list[str],
    qa_checklist: dict[str, Any],
    reviewers: list[str],
    decision_trace: dict[str, Any] | None = None,
    labels: dict[str, str],
) -> str:
    sections = [
        f"### {labels['context']}",
        "",
        ticket_summary or labels["noTicketContext"],
        "",
        f"### {labels['changes']}",
        "",
        implementation_summary or labels["noImplementationSummary"],
        "",
        f"### {labels['filesImpacted']}",
        "",
    ]
    if files_modified:
        sections.extend(f"- `{path}`" for path in files_modified)
    else:
        sections.append(f"- {labels['noFilesRecorded']}")

    sections.extend(["", f"### {labels['risks']}", ""])
    if risks:
        sections.extend(f"- {risk}" for risk in risks)
    else:
        sections.append(f"- {labels['noRisksRecorded']}")

    sections.extend(["", f"### {labels['validation']}", ""])
    sections.append(f"- {labels['build']}: {_format_checklist_value(qa_checklist.get('build'))}")
    sections.append(f"- {labels['tests']}: {_format_checklist_value(qa_checklist.get('tests'))}")
    sections.append(
        f"- {labels['scopeValidation']}: {_format_checklist_value(qa_checklist.get('scopeValidation'))}"
    )

    if decision_trace:
        sections.extend(["", f"### {labels['reasoningSummary']}", ""])
        sections.append(str(decision_trace.get("reasoningSummary") or labels["noReasoningCaptured"]))
        sections.append(
            f"- {labels['overallConfidence']}: {decision_trace.get('overallConfidence', 'unknown')}%"
        )
        for file_decision in decision_trace.get("fileDecisions") or []:
            path = file_decision.get("path")
            sections.extend(["", f"#### {labels['whyFile'].format(path=path)}", ""])
            for reason in file_decision.get("why") or []:
                sections.append(f"- {reason}")
            sections.append(f"- {labels['confidence']}: {file_decision.get('confidence')}%")
            rejected = file_decision.get("rejectedAlternatives") or []
            if rejected:
                sections.append(f"- {labels['rejectedAlternatives']}:")
                sections.extend(f"  - `{alt}`" for alt in rejected)

        risk_assessment = decision_trace.get("riskAssessment") or {}
        if risk_assessment.get("summary"):
            sections.extend(["", f"### {labels['riskAssessment']}", ""])
            sections.extend(f"- {line}" for line in risk_assessment.get("summary") or [])

    sections.extend(["", f"### {labels['recommendedReviewers']}", ""])
    if reviewers:
        sections.extend(f"- {reviewer}" for reviewer in reviewers)
    else:
        sections.append(f"- {labels['noReviewersConfigured']}")

    return "\n".join(sections).strip()


def _collect_risks(
    approved_plan: dict[str, Any],
    code_review_payload: dict[str, Any],
    scope_validation: dict[str, Any],
) -> list[str]:
    risks: list[str] = []
    for source in (
        approved_plan.get("risks") or [],
        code_review_payload.get("risks") or [],
    ):
        for item in source:
            text = str(item).strip()
            if text and text not in risks:
                risks.append(text)

    scope_outcome = str(scope_validation.get("outcome") or "")
    if scope_outcome and scope_outcome not in {"PASS", ""}:
        reason = str(scope_validation.get("reason") or scope_outcome).strip()
        if reason and reason not in risks:
            risks.insert(0, reason)

    return risks[:10]


def _build_qa_checklist(
    code_review_payload: dict[str, Any],
    scope_validation: dict[str, Any],
) -> dict[str, Any]:
    test_run = code_review_payload.get("testRun") or {}
    scope_outcome = str(scope_validation.get("outcome") or "MISSING")
    patch_stats = code_review_payload.get("patchStats") or {}
    touched = _unique_paths(
        list(code_review_payload.get("filesModified") or [])
        + list(code_review_payload.get("filesCreated") or [])
    )
    build_passed = bool(touched)
    if test_run:
        tests_label = "PASS" if test_run.get("passed") else "FAIL"
    else:
        tests_label = "NOT RUN"

    return {
        "build": "PASS" if build_passed else "FAIL",
        "tests": tests_label,
        "scopeValidation": scope_outcome,
        "scopePrecision": scope_validation.get("scopePrecision"),
        "scopeRecall": scope_validation.get("scopeRecall"),
        "linesChanged": patch_stats.get("linesChanged")
        or int(patch_stats.get("linesAdded") or 0) + int(patch_stats.get("linesRemoved") or 0),
        "filesTouched": len(touched),
    }


def _derive_reviewers(context_pack: dict[str, Any], approved_plan: dict[str, Any], labels: dict[str, str]) -> list[str]:
    reviewers: list[str] = []
    repo_id = str(approved_plan.get("targetRepo") or context_pack.get("identified_repo") or "").strip()
    owners = context_pack.get("recommended_reviewers") or context_pack.get("codeowners") or []
    if isinstance(owners, list):
        for item in owners:
            text = str(item).strip()
            if text and text not in reviewers:
                reviewers.append(text)
    if repo_id and repo_id not in reviewers:
        reviewers.append(labels["repositoryOwnerFor"].format(repo_id=repo_id))
    return reviewers[:5]


def _extract_acceptance_criteria(description: str, labels: dict[str, str]) -> str:
    if not description:
        return ""
    for line in description.splitlines():
        cleaned = line.strip()
        lowered = cleaned.lower()
        if lowered.startswith("acceptance criteria") or lowered.startswith(
            labels["acceptanceCriteria"].lower()
        ):
            return cleaned.split(":", 1)[-1].strip()
    return ""


def _unique_paths(paths: list[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in paths:
        path = str(item).strip().replace("\\", "/")
        if not path or path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


def _format_checklist_value(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value)
