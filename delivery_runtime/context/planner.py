"""Repo-aware implementation planner driven by Context Pack."""

from __future__ import annotations

import re
from typing import Any

from delivery_runtime.context.models import ContextPack
from delivery_runtime.context.repo_architecture import format_architecture_for_prompt
from delivery_runtime.readiness.attachment_prompt import summarize_attachment_extracts

WILDCARD_PATTERN = re.compile(r"\*\*?$|/\*\*")


def validate_plan_payload(payload: dict[str, Any]) -> None:
    """Validate a Gate 1 plan payload before persistence."""
    repo = str(payload.get("targetRepo") or "")
    if repo == "unknown" or not repo:
        raise ValueError("Planner must not emit targetRepo='unknown'")
    for path in payload.get("likelyImpactedFiles") or []:
        if WILDCARD_PATTERN.search(str(path)):
            raise ValueError(f"Planner must not emit wildcard paths: {path}")


class RepoAwarePlanner:
    """Produce Gate 1 payloads from a Context Pack."""

    def plan(self, pack: ContextPack) -> dict[str, Any]:
        if not pack.repo_resolved:
            return {
                "needsClarification": True,
                "clarificationReason": (
                    f"No repository could be identified for project "
                    f"{pack.jira_ticket.get('projectKey')}. Update project_mapping.yaml "
                    f"or provide a resolved repo before planning."
                ),
                "contextPack": pack.to_dict(),
            }

        repo_id = str(pack.identified_repo)
        impacted = self._select_impacted_files(pack)
        if not impacted:
            reason = (
                f"Repository {repo_id} is mapped for project "
                f"{pack.jira_ticket.get('projectKey')} but no concrete impacted files "
                f"could be identified."
            )
            notes = [str(note).strip() for note in (pack.build_notes or []) if str(note).strip()]
            if notes:
                reason = f"{reason} {' '.join(notes)}"
            else:
                reason = (
                    f"{reason} Configure checkout_path in project_mapping.yaml "
                    f"or add ticket keywords that match repository structure."
                )
            return {
                "needsClarification": True,
                "clarificationReason": reason,
                "contextPack": pack.to_dict(),
            }

        risks = self._build_risks(pack, impacted)
        understanding = self._build_understanding(pack)
        plan = self._build_plan(pack, impacted)
        confidence = self._confidence(pack, impacted)

        payload = {
            "needsClarification": False,
            "ticketUnderstanding": understanding,
            "jiraContextUsed": {
                **pack.jira_ticket,
                "acceptanceCriteria": pack.acceptance_criteria,
                "commentCount": len(pack.jira_comments),
                "linkedTicketCount": len(pack.linked_tickets),
                "epicKey": (pack.epic or {}).get("key"),
            },
            "targetRepo": repo_id,
            "implementationPlan": plan,
            "likelyImpactedFiles": impacted,
            "risks": risks,
            "confidenceLevel": round(confidence, 2),
            "contextPack": pack.to_dict(),
        }
        validate_plan_payload(payload)
        return payload

    def _select_impacted_files(self, pack: ContextPack) -> list[str]:
        files = list(pack.candidate_files)
        feedback = pack.rejection_feedback.lower()

        if feedback:
            feedback_hits = [
                path
                for path in pack.repo_structure
                if path.endswith((".py", ".ts", ".tsx", ".js", ".sql", ".md"))
                and any(token in path.lower() for token in self._feedback_tokens(feedback))
            ]
            for path in feedback_hits:
                if path not in files:
                    files.insert(0, path)

        if not files and pack.repo_structure:
            fallback = [
                item
                for item in pack.repo_structure
                if item.endswith((".py", ".ts", ".tsx", ".js", ".sql"))
            ][:3]
            files.extend(fallback)

        return files[:5]

    def _build_understanding(self, pack: ContextPack) -> str:
        ticket = pack.jira_ticket
        lines = [
            f"{pack.jira_key} ({ticket.get('issueType')}) targets {ticket.get('summary')}.",
            f"Primary goal: {pack.acceptance_criteria[0] if pack.acceptance_criteria else ticket.get('summary')}.",
        ]
        if pack.epic:
            lines.append(
                f"Epic context: {(pack.epic or {}).get('key')} — {(pack.epic or {}).get('summary') or 'linked epic'}."
            )
        if pack.linked_tickets:
            linked_keys = ", ".join(item["key"] for item in pack.linked_tickets[:3])
            lines.append(f"Linked tickets considered: {linked_keys}.")
        if pack.jira_comments:
            lines.append(f"Latest comment insight: {pack.jira_comments[-1]['body'][:160]}")
        attachment_summary = summarize_attachment_extracts(pack.jira_attachment_extracts)
        if attachment_summary:
            lines.append(attachment_summary)
        if pack.rejection_feedback:
            lines.append(f"Reviewer feedback driving replan: {pack.rejection_feedback}")
        lines.append(f"Repository selected: {pack.identified_repo}.")
        architecture_brief = format_architecture_for_prompt(pack.repo_architecture)
        if architecture_brief:
            lines.append(f"Repository architecture: {architecture_brief.replace(chr(10), ' ')}")
        return " ".join(lines)

    def _build_plan(self, pack: ContextPack, impacted: list[str]) -> str:
        primary = impacted[0]
        test_candidates = [path for path in impacted if "/tests/" in path or ".test." in path]
        test_target = test_candidates[0] if test_candidates else self._guess_test_path(primary)

        lines = [
            f"1. Re-read acceptance criteria for {pack.jira_key} and confirm expected behavior.",
            f"2. Inspect `{primary}` and related modules in `{pack.identified_repo}`.",
        ]

        if pack.rejection_feedback:
            lines.append(f"3. Address reviewer feedback: {pack.rejection_feedback}")
            step = 4
        else:
            step = 3

        lines.extend(
            [
                f"{step}. Implement the minimal fix in `{primary}` aligned with project conventions.",
                f"{step + 1}. Extend or add coverage in `{test_target}` for the acceptance criteria.",
                f"{step + 2}. Document rollback/monitoring notes in the MR description before Gate 1 approval.",
            ]
        )

        if pack.git_history:
            latest = pack.git_history[0]
            lines.append(
                f"{step + 3}. Review recent change `{latest['sha']}` on `{latest['file']}` before editing."
            )

        return "\n".join(lines)

    def _build_risks(self, pack: ContextPack, impacted: list[str]) -> list[str]:
        risks: list[str] = []
        summary = str(pack.jira_ticket.get("summary") or "").lower()
        description = str(pack.jira_ticket.get("description") or "").lower()
        primary_file = impacted[0] if impacted else ""

        if not pack.repo_checkout_path:
            risks.append("Planning used mapped repo metadata without a local checkout scan.")
        if len(pack.acceptance_criteria) <= 1 and len(description) < 40:
            risks.append("Acceptance criteria are thin; validate scope with the reporter before coding.")
        if "render" in summary or "render" in description or "ame" in description or "media offline" in description:
            risks.append("Render and AME pipeline regressions may only reproduce on specific encoder nodes.")
        if "partial checkin" in summary or "checkin" in description or "audio" in description:
            risks.append("Partial checkin audio track mapping can differ between Premiere encoding profiles.")
        if "flex" in description or "workflow" in description or "link-projects" in description:
            risks.append("Flex workflow variables such as link-projects may differ between staging and production.")
        if "localstorage" in summary.replace(" ", "") or "localstorage" in description.replace(" ", ""):
            risks.append("localStorage cache growth can degrade panel responsiveness until pruning runs.")
        if "dbt" in summary or "snowflake" in summary or "gold" in summary:
            risks.append("Gold-layer dbt changes require coordinated tests and Airflow backfill planning.")
        if "notebook" in summary or "scheduler" in summary or "workspace" in summary:
            risks.append("Workspace scheduler notebook failures may hide root cause in platform logs.")
        if "search" in summary or "far" in summary or "targetfield" in summary or "news" in summary:
            risks.append("Search and news query changes require contract tests to avoid API regressions.")
        if pack.rejection_feedback:
            risks.append(
                f"Revised plan must explicitly mitigate reviewer concern: {pack.rejection_feedback}"
            )
        if primary_file and primary_file not in " ".join(risks):
            risks.append(f"Primary change in `{primary_file}` needs regression coverage before merge.")

        return risks[:5]

    def _confidence(self, pack: ContextPack, impacted: list[str]) -> float:
        score = 0.55
        if pack.repo_checkout_path:
            score += 0.1
        if impacted:
            score += 0.1
        if len(pack.acceptance_criteria) >= 2:
            score += 0.08
        if pack.git_history:
            score += 0.05
        if pack.project_conventions:
            score += 0.04
        if pack.rejection_feedback:
            score += 0.03
        return min(score, 0.92)

    @staticmethod
    def _guess_test_path(primary: str) -> str:
        if primary.startswith("src/"):
            candidate = primary.replace("src/", "tests/", 1)
            if candidate.endswith(".ts"):
                return candidate.replace(".ts", ".test.ts")
            if candidate.endswith(".py"):
                return candidate.replace(".py", "_test.py")
            return candidate
        return f"tests/{PathStem(primary)}.test.ts"

    @staticmethod
    def _feedback_tokens(feedback: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z0-9_-]{4,}", feedback.lower())
        extras = {
            "ame": ["render", "ame", "panel", "media"],
            "flex": ["flex", "workflow", "link", "projects"],
            "migration": ["migration", "schema", "rollback"],
            "samesite": ["cookie", "auth", "login"],
        }
        expanded: list[str] = list(tokens)
        for token in tokens:
            expanded.extend(extras.get(token, []))
        return expanded


def PathStem(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    for suffix in (".ts", ".py", ".js", ".sql"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name
