"""Hermes-backed publisher agent (push branch + create GitLab MR)."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable

from delivery_runtime.agents.registry import AgentManifestRegistry
from delivery_runtime.agents.schema import AgentManifest
from delivery_runtime.shadow.context import delivery_agent_role
from lc_server.agent_bridge.manifest_prompt import render_manifest_system_prompt

logger = logging.getLogger(__name__)

_registry = AgentManifestRegistry()

_JSON_BLOCK_RE = re.compile(r"\{[^{}]*\"status\"[^{}]*\}", re.DOTALL)

PUBLISHER_TOOLSETS = ["terminal", "skills"]
PUBLISHER_SYSTEM_PROMPT = """You are the LivingColor Publisher Agent.

Your ONLY job is to publish an already-approved delivery branch to GitLab:
push the branch, ensure the integration branch exists, and create the merge request.
The MR content was written and approved by a human — reproduce it verbatim.

Rules:
- Follow the agent-mr-publisher skill protocol exactly, in order.
- You MUST create and manage the merge request exclusively via GitLab MCP tools
  (create_merge_request, create_branch, and read/list branch tools).
- NEVER use curl, wget, httpie, python -c, or any direct GitLab REST API call.
- NEVER write MR payloads to /tmp or any path outside the Workspace Root.
- Never rewrite, summarize, or translate the MR title or description.
- Never edit files, commit, merge, rebase, or modify the repository content.
  The only git command you may run is git push.
- Stay inside the Workspace Root checkout. Never access parent directories.
- When finished, output a JSON completion block:
  {"mrUrl": "...", "mrIid": 0, "targetBranch": "...", "status": "published"}
  If publication failed, use {"status": "failed", "error": "..."} instead.
"""


class PublisherCompletionError(RuntimeError):
    """Publisher completion was missing, malformed, or reported failure."""


def parse_publisher_completion(text: str) -> dict[str, Any]:
    """Extract and validate the publisher JSON completion block."""
    payload: dict[str, Any] | None = None
    for match in _JSON_BLOCK_RE.finditer(text or ""):
        try:
            candidate = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and "status" in candidate:
            payload = candidate
    if payload is None:
        raise PublisherCompletionError("publisher completion JSON block not found")

    status = str(payload.get("status") or "")
    if status == "failed":
        raise PublisherCompletionError(str(payload.get("error") or "publisher reported failure"))
    if status != "published":
        raise PublisherCompletionError(f"unexpected publisher status: {status!r}")

    mr_iid = payload.get("mrIid")
    mr_url = str(payload.get("mrUrl") or "")
    if not isinstance(mr_iid, int) or isinstance(mr_iid, bool) or not mr_url:
        raise PublisherCompletionError("publisher completion missing mrUrl/mrIid")

    return {
        "mrUrl": mr_url,
        "mrIid": mr_iid,
        "targetBranch": str(payload.get("targetBranch") or ""),
        "status": "published",
    }


def build_publisher_prompt(context: dict[str, Any]) -> str:
    """Assemble the publication instructions for one mr_creation run."""
    workspace_path = str(context.get("workspacePath") or "")
    delivery_branch = str(context.get("deliveryBranch") or "")
    integration_branch = str(context.get("integrationBranch") or "")
    mr_title = str(context.get("mrTitle") or "")
    mr_description = str(context.get("mrDescription") or "")

    if integration_branch:
        integration_section = f"Integration branch (MR target): `{integration_branch}`"
    else:
        integration_section = (
            "Integration branch (MR target): not configured. Resolve the first existing "
            "remote branch among staging, dev, develop, preprod, test; if none exists, "
            "create 'develop' from the repository default branch."
        )

    return "\n".join(
        [
            "Publish the approved delivery branch to GitLab.",
            "",
            f"Workspace Root: {workspace_path}",
            f"Delivery branch to push: `{delivery_branch}`",
            integration_section,
            "",
            "Merge request title (use verbatim, no edits):",
            mr_title,
            "",
            "Merge request description (use verbatim, no edits):",
            mr_description,
            "",
            "Follow the agent-mr-publisher skill protocol exactly: push the delivery branch, "
            "ensure the integration branch exists on the remote, then create the merge request "
            "ONLY with the GitLab MCP create_merge_request tool (no curl, no REST fallbacks).",
            "Finish with the JSON completion block described in your instructions.",
        ]
    )


class HermesPublisherAgent:
    """Runs the Hermes AIAgent loop to push the branch and create the GitLab MR."""

    def __init__(
        self,
        *,
        agent_factory: Callable[..., Any] | None = None,
        registry: AgentManifestRegistry | None = None,
    ) -> None:
        self._agent_factory = agent_factory or _default_publisher_agent_factory
        self._registry = registry or _registry

    def execute(self, work_order_id: str, context: dict[str, Any]) -> dict[str, Any]:
        from delivery_runtime.development.git_branch import commit_delivery_work
        from delivery_runtime.development.scope_contract import build_runtime_scope_contract
        from delivery_runtime.development.scope_enforcement import clear_scope_guard, guard_from_context
        from delivery_runtime.development.workspace_confinement import (
            activate_workspace_runtime,
            deactivate_workspace_runtime,
        )
        from delivery_runtime.mr_drafts.store import set_mr_draft_publication

        workspace = Path(str(context.get("workspacePath") or ""))
        if not workspace.is_dir():
            raise PublisherCompletionError(f"workspace not found: {workspace}")

        delivery_branch = str(context.get("deliveryBranch") or "")
        if not delivery_branch:
            raise PublisherCompletionError("delivery branch missing from publication context")

        # The developer agent leaves its work staged/unstaged (git commit is
        # policy-denied during development) — commit it deterministically here
        # so the publisher never pushes an empty branch.
        jira_key = str(
            context.get("jiraKey")
            or (context.get("workOrder") or {}).get("jiraKey")
            or work_order_id
        )
        commit_message = f"{jira_key}: {str(context.get('mrTitle') or 'delivery work')}"
        commit_delivery_work(workspace, branch=delivery_branch, message=commit_message)

        project_key = str(context.get("projectKey") or "").strip().upper() or None
        manifest = _resolve_publisher_manifest(project_key, registry=self._registry)
        task_id = f"delivery-publish-{work_order_id}"

        runtime_restore: tuple[str | None, object | None] | None = None
        try:
            runtime_restore = activate_workspace_runtime(task_id, workspace, confinement_root=workspace)
            # guard_from_context requires a contract; a workspace-only contract keeps the
            # publisher confined to the checkout while allowing the git push.
            runtime_scope = build_runtime_scope_contract(work_order_id, None, workspace_only=True)
            guard_from_context(
                task_id=task_id,
                workspace=workspace,
                baseline_ref=None,
                scope_contract=runtime_scope.to_dict() if runtime_scope else None,
                allow_git_push=True,
            )
            agent = self._agent_factory(
                task_id=task_id,
                work_order_id=work_order_id,
                project_key=project_key,
                manifest=manifest,
            )
            # GitLab write MCP tools are role-gated in standard mode; the
            # contextvar propagates to concurrent tool workers via
            # tools.thread_context.propagate_context_to_thread.
            with delivery_agent_role("publisher"):
                result = agent.run_conversation(build_publisher_prompt(context), task_id=task_id)
            completion = parse_publisher_completion(str(result.get("final_response") or ""))
        finally:
            clear_scope_guard(task_id)
            if runtime_restore is not None:
                deactivate_workspace_runtime(
                    task_id,
                    previous_terminal_cwd=runtime_restore[0],
                    session_token=runtime_restore[1],
                )

        self._verify_mr_exists(project_key, completion)

        draft_id = str(context.get("draftId") or "")
        if draft_id:
            set_mr_draft_publication(draft_id, mr_url=completion["mrUrl"], mr_iid=completion["mrIid"])
        return completion

    @staticmethod
    def _verify_mr_exists(project_key: str | None, completion: dict[str, Any]) -> None:
        from lc_server.integrations.gitlab_mr_verification import (
            load_project_gitlab_mcp_config,
            repo_path_from_mr_url,
            verify_merge_request_exists,
        )

        mcp_config = load_project_gitlab_mcp_config(project_key or "")
        if not mcp_config:
            raise PublisherCompletionError("No GitLab MCP config found for project")

        try:
            repo_path = repo_path_from_mr_url(completion["mrUrl"])
        except ValueError as exc:
            raise PublisherCompletionError(str(exc)) from exc

        found = verify_merge_request_exists(
            mcp_config=mcp_config,
            repo_path_with_namespace=repo_path,
            mr_iid=completion["mrIid"],
        )
        if found is None:
            raise PublisherCompletionError("MR not found in GitLab after publication")


def _resolve_publisher_manifest(
    project_key: str | None,
    *,
    registry: AgentManifestRegistry,
) -> AgentManifest | None:
    if not project_key:
        return None
    key = project_key.strip().upper()
    if not key:
        return None
    if not registry.is_automation_ready(key):
        return None
    return registry.get(key, "publisher")


def _default_publisher_agent_factory(
    *,
    task_id: str,
    work_order_id: str,
    project_key: str | None,
    manifest: AgentManifest | None,
) -> Any:
    from hermes_cli.config import load_config
    from hermes_cli.fallback_config import get_fallback_chain
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from lc_server.env_loader import prepare_delivery_agent_environment
    from run_agent import AIAgent

    prepare_delivery_agent_environment()

    from lc_server.integrations.project_mcp_runtime import apply_project_mcp_runtime

    apply_project_mcp_runtime(project_key)

    # MCP toolsets (mcp-gitlab-*) are registered only after discover_mcp_tools().
    # Without this, validate_toolset rejects them and the publisher never sees
    # create_merge_request — it falls back to curl/python in the terminal tool.
    try:
        from tools.mcp_tool import discover_mcp_tools

        discover_mcp_tools()
    except Exception:
        logger.warning("Publisher MCP tool discovery failed", exc_info=True)

    os.environ.setdefault("HERMES_YOLO_MODE", "1")
    os.environ.setdefault("HERMES_ACCEPT_HOOKS", "1")

    if manifest:
        system_prompt = render_manifest_system_prompt(manifest)
        base_toolsets = list(manifest.runtime.toolsets) or list(PUBLISHER_TOOLSETS)
        max_iterations = manifest.runtime.max_iterations or 16
        platform = manifest.identity.platform
    else:
        system_prompt = PUBLISHER_SYSTEM_PROMPT
        base_toolsets = list(PUBLISHER_TOOLSETS)
        max_iterations = 16
        platform = "livingcolor-delivery"

    from lc_server.agent_bridge.delivery_toolsets import resolve_publisher_toolsets

    toolsets = resolve_publisher_toolsets(
        base_toolsets=base_toolsets,
        manifest=manifest,
        project_key=project_key,
    )

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
        session_id=f"delivery-publish-{work_order_id}",
        ephemeral_system_prompt=system_prompt,
        skip_context_files=True,
        skip_memory=True,
        fallback_model=fallback or None,
        credential_pool=runtime.get("credential_pool"),
        clarify_callback=_publisher_clarify_callback,
    )
    agent.suppress_status_output = True
    agent.stream_delta_callback = None
    agent.tool_gen_callback = None
    return agent


def _publisher_clarify_callback(question: str, choices=None) -> str:
    if choices:
        return (
            f"[LivingColor publisher mode: no human is available. Choose the best option from "
            f"{choices} and continue the publication protocol.]"
        )
    return (
        "[LivingColor publisher mode: no human is available. Make the most reasonable "
        "assumption and continue the publication protocol; report failure in the JSON "
        "completion block if publication cannot proceed.]"
    )


__all__ = [
    "HermesPublisherAgent",
    "PublisherCompletionError",
    "PUBLISHER_SYSTEM_PROMPT",
    "PUBLISHER_TOOLSETS",
    "build_publisher_prompt",
    "parse_publisher_completion",
]
