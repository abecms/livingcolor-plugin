"""Prompt assembly helpers for development agents (Hermes-free)."""

from __future__ import annotations

import json
from typing import Any

from delivery_runtime.context.repo_architecture import format_architecture_for_prompt
from delivery_runtime.readiness.attachment_prompt import build_attachment_prompt_section
from delivery_runtime.development.phases import (
    DEVELOPER_PHASE_CODE_QUALITY_REVIEW,
    DEVELOPER_PHASE_IMPLEMENT,
    DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION,
    normalize_developer_phase,
)


def build_developer_user_prompt(
    *,
    work_order_id: str,
    jira_key: str,
    approved_plan: dict[str, Any],
    context_pack: dict[str, Any],
    reviewer_feedback: list[dict[str, Any]],
    test_command: list[str] | None,
    scope_contract: dict[str, Any] | None = None,
    workspace_path: str | None = None,
    project_environment_path: str | None = None,
    workspace_only_runtime: bool = False,
    delivery_branch: str | None = None,
    integration_branch: str | None = None,
    merge_target_branch: str | None = None,
    developer_phase: str | None = None,
    merge_conflict: dict[str, Any] | None = None,
) -> str:
    """Build the user message for a development execution turn."""
    phase = normalize_developer_phase(developer_phase)
    acceptance = approved_plan.get("jiraContextUsed", {}).get("acceptanceCriteria") or context_pack.get(
        "acceptance_criteria"
    ) or []
    title = "# LivingColor Developer Agent"
    if phase == DEVELOPER_PHASE_CODE_QUALITY_REVIEW:
        title = "# LivingColor Developer Agent — Thermo-Nuclear Code Quality Review"
    elif phase == DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION:
        title = "# LivingColor Developer Agent — Merge Conflict Resolution"

    sections = [
        title,
        "",
    ]
    if phase == DEVELOPER_PHASE_CODE_QUALITY_REVIEW:
        sections.extend(
            [
                "The implementation patch is complete. Perform the thermo-nuclear code quality review "
                "using skill_view('thermo-nuclear-code-quality-review') before merge toward integration branches.",
                "Improve structure and maintainability without changing product behavior or expanding scope.",
                "",
            ]
        )
    elif phase == DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION:
        sections.extend(
            [
                "The MR draft was approved but merging the integration branch reported conflicts.",
                "Resolve every conflict using skill_view('fix-merge-conflicts') and restore a buildable state.",
                "",
            ]
        )
    else:
        sections.extend(
            [
                "Execute the approved implementation plan below. Do not rewrite or replace the plan.",
                "Make minimal, reviewable changes in the repository checkout.",
                "Before finishing, perform the thermo-nuclear code quality review using "
                "skill_view('thermo-nuclear-code-quality-review'). Improve structure and "
                "maintainability without changing product behavior or expanding scope.",
                "",
            ]
        )

    sections.extend(
        [
            f"Work order: {work_order_id}",
            f"Jira key: {jira_key}",
            "",
        ]
    )
    if workspace_path:
        sections.extend(
            [
                "## Repository checkout (git working tree)",
                "",
                f"`{workspace_path}`",
                "",
                "Run commands from this checkout unless you intentionally need another path "
                "inside the project environment below.",
                "",
            ]
        )
    if project_environment_path:
        sections.extend(
            [
                "## Project environment boundary",
                "",
                f"`{project_environment_path}`",
                "",
                "This folder is the hard boundary for files and shell paths.",
                "You may read, write, install dependencies, and run tests anywhere inside it.",
                "Never access your home directory, LivingColor platform source trees, or paths outside this folder.",
                "",
            ]
        )
    elif workspace_path:
        sections.extend(
            [
                "## Workspace boundary",
                "",
                f"`{workspace_path}`",
                "",
                "Never read, write, cd, or run commands outside this directory.",
                "Do not access the LivingColor platform source tree or developer machine paths.",
                "",
            ]
        )
    if delivery_branch:
        sections.extend(
            [
                "## Delivery branch",
                "",
                f"Work on branch `{delivery_branch}` only.",
                "This branch was created from the production-linked integration branch"
                f" (`{integration_branch or 'main/master/prod'}`).",
                f"The merge request must target the test-environment branch"
                f" (`{merge_target_branch or 'staging/dev/develop/preprod/test'}`).",
                "Do not switch branches, push, or open merge requests.",
                "",
            ]
        )
    if phase == DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION and merge_conflict:
        conflicting = merge_conflict.get("conflictingFiles") or []
        sections.extend(
            [
                "## Merge conflict context",
                "",
                f"Feature branch: `{merge_conflict.get('featureBranch') or delivery_branch or 'current branch'}`",
                f"Created from (prod): `{merge_conflict.get('integrationBranch') or integration_branch or 'main/master/prod'}`",
                f"Merge target (test env): `{merge_conflict.get('mergeTargetBranch') or merge_target_branch or 'staging/dev/develop/preprod/test'}`",
                f"Message: {merge_conflict.get('message') or 'Conflicts detected'}",
                "",
                "### Conflicting files",
                "\n".join(f"- `{path}`" for path in conflicting) or "- Detect via git status",
                "",
            ]
        )
    sections.extend(
        [
            "## Approved implementation plan",
            str(approved_plan.get("implementationPlan") or "").strip(),
            "",
            "## Jira ticket context",
            f"Summary: {context_pack.get('jira_ticket', {}).get('summary') or jira_key}",
            "",
            "### Description",
            str(context_pack.get("jira_ticket", {}).get("description") or "").strip() or "(missing)",
            "",
        ]
    )
    jira_comments = context_pack.get("jira_comments") or []
    if jira_comments:
        sections.extend(
            [
                "### Jira comments",
                "\n".join(
                    f"- **{item.get('author') or 'unknown'}**: {str(item.get('body') or '').strip()}"
                    for item in jira_comments
                    if str(item.get("body") or "").strip()
                ),
                "",
            ]
        )
    attachment_section = build_attachment_prompt_section(
        context_pack.get("jira_attachment_extracts"),
        attachments=(context_pack.get("jira_ticket") or {}).get("attachments"),
    )
    if attachment_section:
        sections.extend([attachment_section, ""])
    sections.extend(
        [
            "## Target repository",
            str(approved_plan.get("targetRepo") or context_pack.get("identified_repo") or ""),
            "",
            "## Likely impacted files",
            "\n".join(f"- `{path}`" for path in approved_plan.get("likelyImpactedFiles") or []),
            "",
        ]
    )
    sections.extend(build_scope_contract_prompt_sections(scope_contract, workspace_only=workspace_only_runtime))
    sections.extend(
        [
            "## Acceptance criteria",
            "\n".join(f"- {item}" for item in acceptance) or "- See Jira ticket summary.",
            "",
            "## Project conventions",
            "\n".join(f"- {item}" for item in context_pack.get("project_conventions") or [])
            or "- Follow AGENTS.md inside the workspace root when present.",
        ]
    )

    architecture_brief = format_architecture_for_prompt(context_pack.get("repo_architecture") or {})
    if architecture_brief:
        sections.extend(
            [
                "",
                "## Repository architecture",
                architecture_brief,
            ]
        )

    if reviewer_feedback:
        sections.extend(
            [
                "",
                "## Structured reviewer feedback (must address)",
                json.dumps(reviewer_feedback, indent=2, sort_keys=True),
            ]
        )

    if test_command:
        sections.extend(
            [
                "",
                "## Verification",
                f"Run `{ ' '.join(test_command) }` before finishing and fix failures caused by your changes.",
            ]
        )

    sections.extend(
        [
            "",
            "## Completion",
            "When done, respond with a short summary and a fenced JSON completion block:",
            "```json",
            json.dumps(
                {
                    "summary": "One sentence describing the patch.",
                    "confidence": 0.0,
                    "risks": ["optional risk notes"],
                },
                indent=2,
            ),
            "```",
        ]
    )
    return "\n".join(sections)


def build_scope_contract_prompt_sections(
    scope_contract: dict[str, Any] | None,
    *,
    workspace_only: bool = False,
) -> list[str]:
    if workspace_only:
        return [
            "",
            "## Runtime scope",
            "",
            "During this run you may modify any file inside the project environment.",
            "The gate-time scope contract below is guidance for the approved plan — it is not a hard tool block.",
            "",
        ]

    if not scope_contract:
        return []

    allowed_files = scope_contract.get("allowedFiles") or []
    allowed_directories = scope_contract.get("allowedDirectories") or []
    forbidden_paths = scope_contract.get("forbiddenPaths") or []
    max_files = scope_contract.get("maxFilesTouched")
    max_lines = scope_contract.get("maxLinesChanged")

    sections = [
        "",
        "## Scope Contract (mandatory)",
        "",
        "You are only allowed to modify files listed in the Scope Contract.",
        "Do not create files outside the allowed directories.",
        "Do not modify forbidden paths.",
        "If implementation requires touching forbidden files, stop and explain why instead of editing them.",
        "",
        "### Allowed files",
        "\n".join(f"- `{path}`" for path in allowed_files) or "- See likely impacted files only.",
        "",
        "### Allowed directories",
        "\n".join(f"- `{path}`" for path in allowed_directories) or "- Parent directories of allowed files only.",
        "",
        "### Forbidden paths",
        "\n".join(f"- `{path}`" for path in forbidden_paths),
        "",
        f"- Maximum files touched: `{max_files}`",
        f"- Maximum lines changed: `{max_lines}`",
    ]
    return sections


def parse_developer_completion(final_response: str) -> dict[str, Any]:
    """Extract optional JSON completion metadata from the agent final response."""
    text = final_response or ""
    start = text.rfind("```json")
    if start == -1:
        return {"summary": text.strip()[:500]}
    payload = text[start + len("```json") :]
    end = payload.find("```")
    if end == -1:
        return {"summary": text.strip()[:500]}
    try:
        parsed = json.loads(payload[:end].strip())
    except json.JSONDecodeError:
        return {"summary": text.strip()[:500]}
    if not isinstance(parsed, dict):
        return {"summary": text.strip()[:500]}
    return parsed
