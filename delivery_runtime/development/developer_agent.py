"""Deterministic developer agent used for validation harnesses and tests."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from delivery_runtime.development.feedback import parse_reviewer_feedback
from delivery_runtime.development.patch_store import save_patch_artifact
from delivery_runtime.development.phases import (
    DEVELOPER_PHASE_CODE_QUALITY_REVIEW,
    DEVELOPER_PHASE_IMPLEMENT,
    DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION,
    normalize_developer_phase,
)
from delivery_runtime.development.workspace import collect_patch_from_workspace, prepare_development_workspace


class HeuristicDeveloperAgent:
    """Executes an approved implementation plan without replanning (deterministic stub)."""

    def execute(self, work_order_id: str, context: dict[str, Any]) -> dict[str, Any]:
        approved_plan = context.get("approvedAnalysisPlan") or {}
        context_pack = context.get("contextPack") or {}
        node_payload = context.get("nodePayload") or {}
        reviewer_feedback = node_payload.get("reviewerFeedback") or context.get("reviewerFeedback") or []
        developer_phase = normalize_developer_phase(
            context.get("developerPhase") or node_payload.get("developerPhase")
        )
        merge_conflict = context.get("mergeConflict") or node_payload.get("mergeConflict") or {}
        workspace_baseline = context.get("workspaceBaseline") or node_payload.get("workspaceBaseline")
        reuse_workspace = developer_phase in {
            DEVELOPER_PHASE_CODE_QUALITY_REVIEW,
            DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION,
        } or bool(context.get("reuseWorkspace"))

        if isinstance(reviewer_feedback, str):
            reviewer_feedback = parse_reviewer_feedback(reviewer_feedback)

        repo_id = str(approved_plan.get("targetRepo") or context_pack.get("identified_repo") or "")
        checkout_path = str(context_pack.get("repo_checkout_path") or "")
        if not checkout_path or not Path(checkout_path).is_dir():
            raise ValueError("Developer Agent requires a local repository checkout in the Context Pack")

        jira_key = str(
            (context.get("workOrder") or {}).get("jiraKey")
            or approved_plan.get("jiraContextUsed", {}).get("jiraKey")
            or work_order_id
        )
        issue_type = str(
            context_pack.get("issueType")
            or context_pack.get("issue_type")
            or approved_plan.get("jiraContextUsed", {}).get("issueType")
            or approved_plan.get("jiraContextUsed", {}).get("issue_type")
            or ""
        )

        workspace, baseline = prepare_development_workspace(
            work_order_id,
            checkout_path,
            jira_key=jira_key if not reuse_workspace else None,
            issue_type=issue_type,
            reuse_existing=reuse_workspace,
            baseline_ref=str(workspace_baseline) if workspace_baseline else None,
        )
        primary_files = [str(item) for item in approved_plan.get("likelyImpactedFiles") or []]
        if not primary_files:
            primary_files = [str(item) for item in context_pack.get("candidate_files") or []][:3]
        if not primary_files:
            raise ValueError("Developer Agent requires concrete target files from the approved plan")

        files_modified: list[str] = []
        files_created: list[str] = []
        if developer_phase == DEVELOPER_PHASE_CODE_QUALITY_REVIEW:
            for rel_path in primary_files[:3]:
                target = workspace / rel_path
                if target.exists():
                    body = target.read_text(encoding="utf-8")
                    marker = "# LivingColor thermo-nuclear quality pass"
                    if marker not in body:
                        target.write_text(body + f"\n\n{marker}\n", encoding="utf-8")
                        files_modified.append(rel_path)
        elif developer_phase == DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION:
            for rel_path in (merge_conflict.get("conflictingFiles") or primary_files[:1]):
                target = workspace / str(rel_path)
                if not target.exists():
                    continue
                body = target.read_text(encoding="utf-8")
                if "<<<<<<<" in body:
                    body = body.replace("<<<<<<< HEAD\n", "").replace("=======\n", "").replace(">>>>>>> main\n", "")
                marker = "# LivingColor merge conflict resolved"
                if marker not in body:
                    target.write_text(body + f"\n\n{marker}\n", encoding="utf-8")
                    files_modified.append(str(rel_path))
        else:
            for rel_path in primary_files[:3]:
                target = workspace / rel_path
                created = not target.exists()
                target.parent.mkdir(parents=True, exist_ok=True)
                self._apply_patch_to_file(
                    target,
                    jira_key=jira_key,
                    approved_plan=approved_plan,
                    reviewer_feedback=reviewer_feedback,
                    created=created,
                )
                if created:
                    files_created.append(rel_path)
                else:
                    files_modified.append(rel_path)

        if developer_phase == DEVELOPER_PHASE_IMPLEMENT:
            test_file = self._ensure_test_file(workspace, primary_files[0], jira_key, reviewer_feedback)
            if test_file:
                rel_test = test_file.relative_to(workspace).as_posix()
                if rel_test not in files_created and rel_test not in files_modified:
                    files_created.append(rel_test)

        diff_text, patch_stats, git_modified, git_created, git_deleted = collect_patch_from_workspace(
            workspace,
            baseline,
        )
        if git_modified or git_created or git_deleted:
            files_modified = git_modified
            files_created = git_created

        summary = self._build_summary(
            jira_key,
            files_modified,
            files_created,
            reviewer_feedback,
            developer_phase=developer_phase,
        )
        from delivery_runtime.development.scope_validator import validate_dev_result_scope

        scope_validation = validate_dev_result_scope(
            context=context,
            files_modified=files_modified,
            files_created=files_created,
            files_deleted=git_deleted,
            patch_stats=patch_stats,
        )
        confidence = self._confidence(
            primary_files,
            files_modified + files_created,
            reviewer_feedback,
            scope_validation=scope_validation,
        )

        artifact_paths = save_patch_artifact(
            work_order_id,
            diff_text=diff_text,
            execution_report={
                "filesModified": files_modified,
                "filesCreated": files_created,
                "filesDeleted": git_deleted,
                "summary": summary,
                "patchStats": patch_stats,
                "confidence": confidence,
                "reviewerFeedbackApplied": reviewer_feedback,
                "backend": "heuristic",
                "scopeValidation": scope_validation,
            },
        )

        return {
            "filesModified": files_modified,
            "filesCreated": files_created,
            "filesDeleted": git_deleted,
            "summary": summary,
            "patchStats": patch_stats,
            "confidence": confidence,
            "diffPreview": diff_text[:8000],
            "patchArtifactPath": str(artifact_paths.patch_path),
            "reportArtifactPath": str(artifact_paths.report_path),
            "workspacePath": str(workspace),
            "workspaceBaseline": baseline,
            "developerPhase": developer_phase,
            "reviewerFeedbackApplied": reviewer_feedback,
            "approvedPlanRef": {
                "targetRepo": repo_id,
                "likelyImpactedFiles": primary_files,
            },
            "backend": "heuristic",
            "scopeValidation": scope_validation,
        }

    @staticmethod
    def _apply_patch_to_file(
        target: Path,
        *,
        jira_key: str,
        approved_plan: dict[str, Any],
        reviewer_feedback: list[dict[str, Any]],
        created: bool,
    ) -> None:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", jira_key).lower().strip("_")
        marker = f"LivingColor delivery patch for {jira_key}"
        feedback_lines = [
            f"- [{item.get('type', 'note')}] {item.get('message', '')}".strip()
            for item in reviewer_feedback
            if item.get("message")
        ]
        feedback_block = "\n".join(feedback_lines)

        if target.suffix == ".py":
            body = target.read_text(encoding="utf-8") if target.exists() else ""
            if marker not in body:
                addition = (
                    f"\n\n# {marker}\n"
                    f"def delivery_fix_{slug}():\n"
                    f'    """Execute approved plan for {jira_key}."""\n'
                    f"    return '{approved_plan.get('implementationPlan', '')[:120]}'\n"
                )
                if feedback_block:
                    addition += f"\n# Reviewer feedback addressed:\n# {feedback_block.replace(chr(10), chr(10) + '# ')}\n"
                target.write_text(body + addition, encoding="utf-8")
            elif feedback_block and feedback_block not in body:
                target.write_text(
                    body + f"\n# Reviewer feedback addressed:\n# {feedback_block.replace(chr(10), chr(10) + '# ')}\n",
                    encoding="utf-8",
                )
            return

        if target.suffix in {".ts", ".tsx", ".js", ".jsx"}:
            body = target.read_text(encoding="utf-8") if target.exists() else ""
            if marker not in body:
                fn_name = f"deliveryFix{slug.replace('_', '').title()}"
                addition = (
                    f"\n\n// {marker}\n"
                    f"export function {fn_name}(): string {{\n"
                    f"  return `{approved_plan.get('implementationPlan', '')[:120]}`;\n"
                    f"}}\n"
                )
                if feedback_block:
                    addition += f"// Reviewer feedback addressed:\n// {feedback_block.replace(chr(10), chr(10) + '// ')}\n"
                target.write_text(body + addition, encoding="utf-8")
            elif feedback_block and feedback_block not in body:
                target.write_text(
                    body + f"// Reviewer feedback addressed:\n// {feedback_block.replace(chr(10), chr(10) + '// ')}\n",
                    encoding="utf-8",
                )
            return

        if target.suffix == ".sql":
            body = target.read_text(encoding="utf-8") if target.exists() else ""
            if marker not in body:
                target.write_text(
                    body + f"\n-- {marker}\n-- reviewer notes: {feedback_block or 'n/a'}\n",
                    encoding="utf-8",
                )
            return

        if created:
            target.write_text(f"{marker}\n{feedback_block}\n", encoding="utf-8")

    @staticmethod
    def _ensure_test_file(
        workspace: Path,
        primary_rel: str,
        jira_key: str,
        reviewer_feedback: list[dict[str, Any]],
    ) -> Path | None:
        primary = workspace / primary_rel
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", jira_key).lower().strip("_")
        if primary.suffix == ".py":
            test_path = workspace / "tests" / f"test_delivery_{slug}.py"
            if not test_path.exists():
                test_path.parent.mkdir(parents=True, exist_ok=True)
                feedback_note = reviewer_feedback[0]["message"] if reviewer_feedback else "approved plan"
                test_path.write_text(
                    f'def test_delivery_fix_{slug}():\n'
                    f'    assert "{feedback_note}"\n',
                    encoding="utf-8",
                )
            return test_path
        if primary.suffix in {".ts", ".tsx"}:
            test_path = primary.parent / primary.name.replace(".ts", ".delivery.test.ts")
            if not test_path.exists():
                test_path.write_text(
                    f"describe('{jira_key} delivery patch', () => {{\n"
                    f"  it('covers approved plan', () => {{\n"
                    f"    expect(true).toBe(true);\n"
                    f"  }});\n"
                    f"}});\n",
                    encoding="utf-8",
                )
            return test_path
        return None

    @staticmethod
    def _build_summary(
        jira_key: str,
        files_modified: list[str],
        files_created: list[str],
        reviewer_feedback: list[dict[str, Any]],
        *,
        developer_phase: str = DEVELOPER_PHASE_IMPLEMENT,
    ) -> str:
        touched = files_modified + files_created
        if developer_phase == DEVELOPER_PHASE_CODE_QUALITY_REVIEW:
            base = f"Thermo-nuclear code quality review for {jira_key} touching {len(touched)} file(s)."
        elif developer_phase == DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION:
            base = f"Resolved merge conflicts for {jira_key} touching {len(touched)} file(s)."
        else:
            base = f"Generated reviewable patch for {jira_key} touching {len(touched)} file(s)."
        if reviewer_feedback:
            base += f" Addressed {len(reviewer_feedback)} reviewer note(s)."
        return base

    @staticmethod
    def _confidence(
        predicted_files: list[str],
        touched_files: list[str],
        reviewer_feedback: list[dict[str, Any]],
        scope_validation: dict[str, Any] | None = None,
    ) -> float:
        score = 0.65
        if touched_files:
            score += 0.1
        overlap = set(predicted_files) & set(touched_files)
        if overlap:
            score += 0.1
        if reviewer_feedback:
            score += 0.05
        outcome = (scope_validation or {}).get("outcome")
        if outcome == "PASS":
            score += 0.08
        elif outcome == "SCOPE_VIOLATION":
            score -= 0.35
        elif outcome == "SCOPE_EXPLOSION":
            score -= 0.25
        return min(max(score, 0.0), 0.9)


# Backward-compatible alias for tests and validation harnesses.
DeveloperAgent = HeuristicDeveloperAgent
