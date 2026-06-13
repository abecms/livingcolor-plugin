"""Hermes-backed LivingColor Developer Agent."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

from delivery_runtime.development.feedback import parse_reviewer_feedback
from delivery_runtime.development.patch_store import save_patch_artifact
from delivery_runtime.development.prompt_context import build_developer_user_prompt, parse_developer_completion
from delivery_runtime.context.repo_checkout import (
    ensure_managed_checkout,
    has_clone_credentials,
    is_managed_repo_checkout,
    managed_checkout_path,
    managed_project_environment_root,
)
from delivery_runtime.development.scope_contract import build_runtime_scope_contract
from delivery_runtime.development.scope_enforcement import (
    SCOPE_VIOLATION_BLOCKED,
    clear_scope_guard,
    guard_from_context,
)
from delivery_runtime.development.workspace_confinement import (
    WORKSPACE_VIOLATION,
    activate_workspace_runtime,
    clear_workspace_confinement,
    deactivate_workspace_runtime,
    get_workspace_confinement,
)
from delivery_runtime.development.test_runner import detect_test_command, run_project_tests
from delivery_runtime.agents.registry import AgentManifestRegistry
from delivery_runtime.agents.schema import AgentManifest
from delivery_runtime.development.workspace import collect_patch_from_workspace, prepare_development_workspace
from delivery_runtime.development.phases import (
    DEVELOPER_PHASE_CODE_QUALITY_REVIEW,
    DEVELOPER_PHASE_IMPLEMENT,
    DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION,
    normalize_developer_phase,
)
from lc_server.agent_bridge.manifest_prompt import render_manifest_system_prompt
from lc_server.integrations.jira_attachment_extract import merge_attachment_context_into_pack
from lc_server.integrations.skills import external_guidance_for_skills

logger = logging.getLogger(__name__)

_registry = AgentManifestRegistry()

DEVELOPER_TOOLSETS = ["file", "terminal", "skills"]
DEVELOPER_SYSTEM_PROMPT = """You are the LivingColor Developer Agent.

Your job is to EXECUTE an already-approved implementation plan in a real repository checkout.
You must NOT rewrite, replace, or expand the implementation plan.

Rules:
- Stay inside the Project Environment (e.g. ~/.livingcolor/{PROJECT_KEY}). Never access your home directory, LivingColor platform source trees, or paths outside that project folder.
- The repository checkout under the project environment is your working directory for git changes on the delivery branch.
- You may read, write, install dependencies, run tests, and touch any file inside the project environment when needed (including node_modules, lockfiles, and build output).
- Prefer minimal, reviewable diffs aligned with the approved plan, but do not stop solely because a path is generated or vendor-owned.
- Use repository tools to read, edit, and verify code.
- Run the project's tests when instructed and fix failures caused by your changes.
- Never create merge requests, push branches, or update Jira.
- Work on the prepared per-ticket branch only (`fix/{JIRA-KEY}` or `feature/{JIRA-KEY}`).
- Branch from the production-linked integration branch (`main`, `master`, or `prod`).
- The delivery merge request targets the test-environment branch (`staging`, `dev`, `develop`, `preprod`, or `test`).
- If you cannot complete the fix inside the project environment, stop and explain why.
- When finished, provide a concise summary and the requested JSON completion block.
"""


class HermesDeveloperAgent:
    """Runs the Hermes AIAgent loop against an isolated checkout workspace."""

    def __init__(
        self,
        *,
        agent_factory: Callable[..., Any] | None = None,
        max_iterations: int = 60,
    ) -> None:
        self._agent_factory = agent_factory or _default_agent_factory
        self._max_iterations = max_iterations

    def execute(self, work_order_id: str, context: dict[str, Any]) -> dict[str, Any]:
        context_pack = context.get("contextPack") or {}
        context_pack = merge_attachment_context_into_pack(context_pack, context.get("jiraSnapshot"))
        approved_plan = context.get("approvedAnalysisPlan") or {}
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
        jira_key = str(
            (context.get("workOrder") or {}).get("jiraKey")
            or approved_plan.get("jiraContextUsed", {}).get("jiraKey")
            or work_order_id
        )
        project_key = _resolve_developer_project_key(context, context_pack, approved_plan, jira_key)
        checkout_path = _resolve_repo_checkout_path(
            checkout_path=str(context_pack.get("repo_checkout_path") or ""),
            repo_id=repo_id,
            project_key=project_key,
            context_pack=context_pack,
        )
        context_pack["repo_checkout_path"] = checkout_path
        context["contextPack"] = context_pack

        primary_files = [str(item) for item in approved_plan.get("likelyImpactedFiles") or []]
        if not primary_files:
            primary_files = [str(item) for item in context_pack.get("candidate_files") or []][:5]
        if not primary_files:
            raise ValueError("Developer Agent requires concrete target files from the approved plan")

        issue_type = str(
            context_pack.get("issueType")
            or context_pack.get("issue_type")
            or approved_plan.get("jiraContextUsed", {}).get("issueType")
            or approved_plan.get("jiraContextUsed", {}).get("issue_type")
            or ""
        )

        from delivery_runtime.development.git_branch import (
            format_delivery_branch_name,
            resolve_integration_branch,
            resolve_merge_target_branch,
        )

        delivery_branch = format_delivery_branch_name(jira_key, issue_type)
        workspace, baseline = prepare_development_workspace(
            work_order_id,
            checkout_path,
            jira_key=jira_key if not reuse_workspace else None,
            issue_type=issue_type,
            reuse_existing=reuse_workspace,
            baseline_ref=str(workspace_baseline) if workspace_baseline else None,
        )
        integration_branch = (
            context.get("integrationBranch")
            or node_payload.get("integrationBranch")
            or merge_conflict.get("integrationBranch")
        )
        merge_target_branch = (
            context.get("mergeTargetBranch")
            or node_payload.get("mergeTargetBranch")
            or merge_conflict.get("mergeTargetBranch")
        )
        if (workspace / ".git").exists():
            if not integration_branch:
                try:
                    integration_branch = resolve_integration_branch(workspace)
                except ValueError:
                    integration_branch = None
            if not merge_target_branch:
                try:
                    merge_target_branch = resolve_merge_target_branch(workspace)
                except ValueError:
                    merge_target_branch = None

        test_command = detect_test_command(workspace, context_pack, target_files=primary_files)
        managed_checkout = is_managed_repo_checkout(workspace)
        project_environment = (
            str(managed_project_environment_root(workspace)) if managed_checkout else None
        )
        prompt = build_developer_user_prompt(
            work_order_id=work_order_id,
            jira_key=jira_key,
            approved_plan=approved_plan,
            context_pack=context_pack,
            reviewer_feedback=reviewer_feedback,
            test_command=test_command,
            scope_contract=context.get("scopeContract"),
            workspace_path=str(workspace),
            project_environment_path=project_environment,
            workspace_only_runtime=managed_checkout,
            delivery_branch=delivery_branch,
            integration_branch=integration_branch,
            merge_target_branch=merge_target_branch,
            developer_phase=developer_phase,
            merge_conflict=merge_conflict if developer_phase == DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION else None,
        )
        prompt = _append_external_code_review_guidance(prompt, developer_phase=developer_phase)

        task_id = f"delivery-dev-{work_order_id}"
        scope_guard = None
        workspace_guard = None
        runtime_restore: tuple[str | None, object | None] | None = None
        confinement_root = Path(project_environment) if project_environment else workspace
        runtime_restore = activate_workspace_runtime(
            task_id,
            workspace,
            confinement_root=confinement_root,
        )
        self._register_workspace(task_id, workspace)
        workspace_guard = get_workspace_confinement(task_id)
        runtime_scope = build_runtime_scope_contract(
            work_order_id,
            context.get("scopeContract"),
            workspace_only=managed_checkout,
        )
        scope_guard = guard_from_context(
            task_id=task_id,
            workspace=workspace,
            baseline_ref=baseline,
            scope_contract=runtime_scope.to_dict() if runtime_scope else None,
            allow_git_write=developer_phase == DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION,
        )
        agent = self._agent_factory(
            task_id=task_id,
            work_order_id=work_order_id,
            max_iterations=self._max_iterations,
            project_key=project_key,
        )

        development_started = time.monotonic()
        result: dict[str, Any] = {"final_response": "", "completed": False}
        completion: dict[str, Any] = {}
        try:
            result = agent.run_conversation(prompt, task_id=task_id)
            final_response = str(result.get("final_response") or "")
            completion = parse_developer_completion(final_response)
        finally:
            self._clear_workspace(task_id)
            clear_scope_guard(task_id)
            if runtime_restore is not None:
                deactivate_workspace_runtime(task_id, previous_terminal_cwd=runtime_restore[0], session_token=runtime_restore[1])
        development_duration = time.monotonic() - development_started

        if workspace_guard and workspace_guard.blocked:
            return _blocked_workspace_development_result(
                work_order_id=work_order_id,
                jira_key=jira_key,
                workspace=workspace,
                workspace_guard=workspace_guard,
                approved_plan=approved_plan,
                hermes_metrics=_extract_hermes_metrics(result, development_duration, 0.0),
                reviewer_feedback=reviewer_feedback,
                repo_id=repo_id,
                primary_files=primary_files,
            )

        if scope_guard and scope_guard.blocked:
            return _blocked_scope_development_result(
                work_order_id=work_order_id,
                jira_key=jira_key,
                workspace=workspace,
                scope_guard=scope_guard,
                approved_plan=approved_plan,
                context=context,
                hermes_metrics=_extract_hermes_metrics(result, development_duration, 0.0),
                reviewer_feedback=reviewer_feedback,
                repo_id=repo_id,
                primary_files=primary_files,
            )

        test_started = time.monotonic()
        test_result = run_project_tests(workspace, context_pack, target_files=primary_files)
        tests_duration = time.monotonic() - test_started
        hermes_metrics = _extract_hermes_metrics(result, development_duration, tests_duration)
        diff_text, patch_stats, files_modified, files_created, files_deleted = collect_patch_from_workspace(
            workspace,
            baseline,
            scope_guard=scope_guard,
        )

        if scope_guard and scope_guard.blocked:
            return _blocked_scope_development_result(
                work_order_id=work_order_id,
                jira_key=jira_key,
                workspace=workspace,
                scope_guard=scope_guard,
                approved_plan=approved_plan,
                context=context,
                hermes_metrics=hermes_metrics,
                reviewer_feedback=reviewer_feedback,
                repo_id=repo_id,
                primary_files=primary_files,
            )

        if not files_modified and not files_created and not files_deleted:
            if developer_phase == DEVELOPER_PHASE_IMPLEMENT:
                raise RuntimeError("Hermes Developer Agent finished without producing a patch")

        from delivery_runtime.development.scope_validator import validate_dev_result_scope

        validation_context = dict(context)
        if managed_checkout:
            validation_context["runtimeWorkspaceOnly"] = True
        scope_validation = validate_dev_result_scope(
            context=validation_context,
            files_modified=files_modified,
            files_created=files_created,
            files_deleted=files_deleted,
            patch_stats=patch_stats,
        )

        summary = str(completion.get("summary") or "").strip() or _default_summary(
            jira_key,
            files_modified,
            files_created,
            reviewer_feedback,
        )
        confidence = _confidence(
            primary_files=primary_files,
            touched_files=files_modified + files_created,
            reviewer_feedback=reviewer_feedback,
            completion=completion,
            tests_passed=test_result.passed if test_result else None,
            scope_validation=scope_validation,
        )
        risks = completion.get("risks") if isinstance(completion.get("risks"), list) else []

        artifact_paths = save_patch_artifact(
            work_order_id,
            diff_text=diff_text,
            execution_report={
                "filesModified": files_modified,
                "filesCreated": files_created,
                "filesDeleted": files_deleted,
                "summary": summary,
                "patchStats": patch_stats,
                "confidence": confidence,
                "reviewerFeedbackApplied": reviewer_feedback,
                "backend": "hermes",
                "testRun": test_result.to_dict() if test_result else None,
                "agentCompleted": bool(result.get("completed", True)),
                "risks": risks,
                "hermesMetrics": hermes_metrics,
                "scopeValidation": scope_validation,
            },
        )

        return {
            "filesModified": files_modified,
            "filesCreated": files_created,
            "filesDeleted": files_deleted,
            "summary": summary,
            "patchStats": patch_stats,
            "confidence": confidence,
            "diffPreview": diff_text[:8000],
            "patchArtifactPath": str(artifact_paths.patch_path),
            "reportArtifactPath": str(artifact_paths.report_path),
            "workspacePath": str(workspace),
            "workspaceBaseline": baseline,
            "deliveryBranch": delivery_branch,
            "integrationBranch": integration_branch,
            "mergeTargetBranch": merge_target_branch,
            "developerPhase": developer_phase,
            "reviewerFeedbackApplied": reviewer_feedback,
            "approvedPlanRef": {
                "targetRepo": repo_id,
                "likelyImpactedFiles": primary_files,
            },
            "backend": "hermes",
            "testRun": test_result.to_dict() if test_result else None,
            "risks": risks,
            "hermesMetrics": hermes_metrics,
            "scopeValidation": scope_validation,
        }

    @staticmethod
    def _register_workspace(task_id: str, workspace: Path) -> None:
        from tools.terminal_tool import register_task_env_overrides

        register_task_env_overrides(task_id, {"cwd": str(workspace)})

    @staticmethod
    def _clear_workspace(task_id: str) -> None:
        from tools.terminal_tool import clear_task_env_overrides

        clear_task_env_overrides(task_id)


def _append_external_code_review_guidance(prompt: str, *, developer_phase: str) -> str:
    if developer_phase != DEVELOPER_PHASE_CODE_QUALITY_REVIEW:
        return prompt
    guidance = external_guidance_for_skills(
        ("code-architect", "qa-reviewer", "security-auditor")
    )
    if not guidance:
        return prompt
    return f"{prompt}\n\n{guidance}"


def _resolve_developer_project_key(
    context: dict[str, Any],
    context_pack: dict[str, Any],
    approved_plan: dict[str, Any],
    jira_key: str,
) -> str | None:
    work_order = context.get("workOrder") or {}
    jira_ticket = context_pack.get("jira_ticket") or {}
    jira_context = approved_plan.get("jiraContextUsed") or {}
    for candidate in (
        context.get("projectKey"),
        work_order.get("projectKey"),
        jira_ticket.get("projectKey"),
        jira_context.get("projectKey"),
    ):
        key = str(candidate or "").strip().upper()
        if key:
            return key
    parts = jira_key.split("-")
    if len(parts) >= 2 and parts[0].strip():
        return parts[0].strip().upper()
    return None


def _resolve_repo_checkout_path(
    *,
    checkout_path: str,
    repo_id: str,
    project_key: str | None,
    context_pack: dict[str, Any],
) -> str:
    if checkout_path and Path(checkout_path).is_dir():
        return checkout_path

    if not repo_id:
        raise ValueError(
            "Developer Agent requires a target repository (targetRepo or identified_repo in the Context Pack)"
        )

    if not project_key:
        raise ValueError(
            "Developer Agent requires a project key to clone the repository into the managed checkout path"
        )

    from delivery_runtime.readiness.project_mapping import load_project_mapping

    mapping = load_project_mapping()
    project_cfg = mapping.get(project_key) or mapping.get(project_key.lower()) or {}
    if not isinstance(project_cfg, dict):
        project_cfg = {}

    expected_path = managed_checkout_path(project_key, repo_id)
    cloned = ensure_managed_checkout(
        project_key=project_key,
        repo_id=repo_id,
        project_cfg=project_cfg,
    )
    if cloned and Path(cloned).is_dir():
        context_pack["repo_checkout_path"] = cloned
        return cloned

    if not has_clone_credentials(project_cfg, project_key=project_key):
        from lc_server.integrations.vcs.provider import normalize_vcs_provider

        provider = normalize_vcs_provider(project_cfg.get("vcs"))
        raise ValueError(
            "Developer Agent requires a local repository checkout at "
            f"{expected_path}. {provider.title()} credentials are missing for project {project_key} "
            f"(configure integrations.mcp_servers.{provider} in project_mapping.yaml or global Hermes MCP)."
        )
    raise ValueError(
        "Developer Agent requires a local repository checkout at "
        f"{expected_path}. git clone failed for {repo_id}."
    )


def _blocked_workspace_development_result(
    *,
    work_order_id: str,
    jira_key: str,
    workspace: Path,
    workspace_guard,
    approved_plan: dict[str, Any],
    hermes_metrics: dict[str, Any],
    reviewer_feedback: list[dict[str, Any]],
    repo_id: str,
    primary_files: list[str],
) -> dict[str, Any]:
    from delivery_runtime.development.scope_validator import predicted_files_from_plan

    scope_validation = {
        "outcome": WORKSPACE_VIOLATION,
        "reason": workspace_guard.block_reason or "Development halted by workspace confinement.",
        "predictedFiles": predicted_files_from_plan(approved_plan),
        "touchedFiles": [],
        "scopePrecision": 0.0,
        "scopeRecall": 0.0,
        "violations": [workspace_guard.block_reason or WORKSPACE_VIOLATION],
        "workspaceViolationEvents": workspace_guard.violation_events,
    }
    summary = (
        f"Hermes development for {jira_key} was halted by workspace confinement: "
        f"{scope_validation['reason']}"
    )
    return {
        "filesModified": [],
        "filesCreated": [],
        "filesDeleted": [],
        "summary": summary,
        "patchStats": {"linesAdded": 0, "linesRemoved": 0, "linesChanged": 0, "filesChanged": 0},
        "confidence": 0.1,
        "diffPreview": "",
        "patchArtifactPath": "",
        "reportArtifactPath": "",
        "workspacePath": str(workspace),
        "reviewerFeedbackApplied": reviewer_feedback,
        "approvedPlanRef": {"targetRepo": repo_id, "likelyImpactedFiles": primary_files},
        "backend": "hermes",
        "testRun": None,
        "risks": ["Workspace confinement blocked an out-of-root operation."],
        "hermesMetrics": hermes_metrics,
        "scopeValidation": scope_validation,
    }


def _blocked_scope_development_result(
    *,
    work_order_id: str,
    jira_key: str,
    workspace: Path,
    scope_guard,
    approved_plan: dict[str, Any],
    context: dict[str, Any],
    hermes_metrics: dict[str, Any],
    reviewer_feedback: list[dict[str, Any]],
    repo_id: str,
    primary_files: list[str],
) -> dict[str, Any]:
    from delivery_runtime.development.scope_validator import predicted_files_from_plan

    scope_validation = {
        "outcome": SCOPE_VIOLATION_BLOCKED,
        "reason": scope_guard.block_reason or "Development halted by hard scope enforcement.",
        "predictedFiles": predicted_files_from_plan(approved_plan),
        "touchedFiles": scope_guard.blocked_paths,
        "scopePrecision": 0.0,
        "scopeRecall": 0.0,
        "violations": [scope_guard.block_reason or "SCOPE_VIOLATION_BLOCKED"],
        "enforcementEvents": scope_guard.block_events,
    }
    scope_guard.rollback_to_clean()
    summary = (
        f"Hermes development for {jira_key} was halted by hard scope enforcement: "
        f"{scope_validation['reason']}"
    )
    return {
        "filesModified": [],
        "filesCreated": [],
        "filesDeleted": [],
        "summary": summary,
        "patchStats": {"linesAdded": 0, "linesRemoved": 0, "linesChanged": 0, "filesChanged": 0},
        "confidence": 0.1,
        "diffPreview": "",
        "patchArtifactPath": "",
        "reportArtifactPath": "",
        "workspacePath": str(workspace),
        "reviewerFeedbackApplied": reviewer_feedback,
        "approvedPlanRef": {
            "targetRepo": repo_id,
            "likelyImpactedFiles": primary_files,
        },
        "backend": "hermes",
        "testRun": None,
        "risks": ["Scope expansion required — patch was not produced."],
        "hermesMetrics": hermes_metrics,
        "scopeValidation": scope_validation,
    }


def _resolve_developer_manifest(
    project_key: str | None,
    *,
    registry: AgentManifestRegistry | None = None,
) -> AgentManifest | None:
    if not project_key:
        return None
    key = project_key.strip().upper()
    if not key:
        return None
    active_registry = registry or _registry
    if not active_registry.is_automation_ready(key):
        return None
    return active_registry.get(key, "developer")


def _developer_runtime_config(
    project_key: str | None,
    *,
    default_max_iterations: int,
    registry: AgentManifestRegistry | None = None,
) -> tuple[str, list[str], int, str]:
    manifest = _resolve_developer_manifest(project_key, registry=registry)
    if manifest:
        return (
            render_manifest_system_prompt(manifest),
            list(manifest.runtime.toolsets) or list(DEVELOPER_TOOLSETS),
            manifest.runtime.max_iterations or default_max_iterations,
            manifest.identity.platform,
        )
    return DEVELOPER_SYSTEM_PROMPT, list(DEVELOPER_TOOLSETS), default_max_iterations, "livingcolor-delivery"


def _default_agent_factory(
    *,
    task_id: str,
    work_order_id: str,
    max_iterations: int,
    project_key: str | None = None,
) -> Any:
    from hermes_cli.config import load_config
    from hermes_cli.fallback_config import get_fallback_chain
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from lc_server.env_loader import prepare_delivery_agent_environment
    from run_agent import AIAgent

    prepare_delivery_agent_environment()

    os.environ.setdefault("HERMES_YOLO_MODE", "1")
    os.environ.setdefault("HERMES_ACCEPT_HOOKS", "1")

    system_prompt, toolsets, max_iterations, platform = _developer_runtime_config(
        project_key,
        default_max_iterations=max_iterations,
    )

    manifest = _resolve_developer_manifest(project_key)
    from lc_server.agent_bridge.inference_config import resolve_delivery_inference
    from lc_server.model_defaults import (
        LIVINGCOLOR_DEVELOPER_MODEL,
        LIVINGCOLOR_DEVELOPER_PROVIDER,
    )

    effective_model, effective_provider = resolve_delivery_inference(
        manifest=manifest,
        role_default_model=LIVINGCOLOR_DEVELOPER_MODEL,
        role_default_provider=LIVINGCOLOR_DEVELOPER_PROVIDER,
        allow_env_override=True,
    )

    cfg = load_config()
    runtime = resolve_runtime_provider(
        requested=effective_provider,
        target_model=effective_model or None,
    )
    fallback = get_fallback_chain(cfg)

    agent = AIAgent(
        api_key=runtime.get("api_key"),
        base_url=runtime.get("base_url"),
        provider=runtime.get("provider"),
        api_mode=runtime.get("api_mode"),
        model=effective_model,
        enabled_toolsets=toolsets,
        max_iterations=max_iterations,
        quiet_mode=True,
        platform=platform,
        session_id=f"delivery-{work_order_id}",
        ephemeral_system_prompt=system_prompt,
        skip_context_files=True,
        skip_memory=True,
        fallback_model=fallback or None,
        credential_pool=runtime.get("credential_pool"),
        clarify_callback=_delivery_clarify_callback,
    )
    agent.suppress_status_output = True
    agent.stream_delta_callback = None
    agent.tool_gen_callback = None
    return agent


def _delivery_clarify_callback(question: str, choices=None) -> str:
    if choices:
        return (
            f"[LivingColor delivery mode: no human is available. Choose the best option from "
            f"{choices} and continue executing the approved plan.]"
        )
    return (
        "[LivingColor delivery mode: no human is available. Make the most reasonable "
        "assumption and continue executing the approved plan.]"
    )


def _default_summary(
    jira_key: str,
    files_modified: list[str],
    files_created: list[str],
    reviewer_feedback: list[dict[str, Any]],
) -> str:
    touched = files_modified + files_created
    summary = f"Hermes developer patch for {jira_key} touching {len(touched)} file(s)."
    if reviewer_feedback:
        summary += f" Addressed {len(reviewer_feedback)} reviewer note(s)."
    return summary


def _confidence(
    *,
    primary_files: list[str],
    touched_files: list[str],
    reviewer_feedback: list[dict[str, Any]],
    completion: dict[str, Any],
    tests_passed: bool | None,
    scope_validation: dict[str, Any] | None = None,
) -> float:
    if isinstance(completion.get("confidence"), (int, float)):
        score = float(completion["confidence"])
    else:
        score = 0.6
    if touched_files:
        score += 0.05
    if set(primary_files) & set(touched_files):
        score += 0.1
    if reviewer_feedback:
        score += 0.03
    if tests_passed is True:
        score += 0.12
    elif tests_passed is False:
        score -= 0.15
    outcome = (scope_validation or {}).get("outcome")
    if outcome == "PASS":
        score += 0.08
    elif outcome == "SCOPE_VIOLATION":
        score -= 0.35
    elif outcome == "SCOPE_EXPLOSION":
        score -= 0.25
    return max(0.0, min(score, 0.95))


def _extract_hermes_metrics(
    result: dict[str, Any],
    development_duration_seconds: float,
    tests_duration_seconds: float,
) -> dict[str, Any]:
    messages = result.get("messages") or []
    tool_calls = 0
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "assistant":
            tool_calls += len(message.get("tool_calls") or [])
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else None
    return {
        "planningDurationSeconds": 0.0,
        "developmentDurationSeconds": round(development_duration_seconds, 2),
        "testsDurationSeconds": round(tests_duration_seconds, 2),
        "tokenUsage": usage,
        "toolCalls": tool_calls or int(result.get("api_calls") or 0),
    }
