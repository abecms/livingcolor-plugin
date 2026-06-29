"""Deterministic publisher for heuristic/cloud delivery runs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from delivery_runtime.development.git_branch import commit_delivery_work
from delivery_runtime.mr_drafts.store import set_mr_draft_publication
from delivery_runtime.readiness.project_settings import (
    load_project_vcs_provider,
    resolve_project_mcp_server,
)
from lc_server.agent_bridge.heuristic_publisher import (
    create_github_pull_request,
    find_existing_github_pull_request,
    push_delivery_branch,
)
from lc_server.agent_bridge.hermes_publisher import PublisherCompletionError
from lc_server.integrations.vcs.github import github_token_from_config
from lc_server.integrations.vcs.provider import normalize_vcs_provider

logger = logging.getLogger(__name__)


class HeuristicPublisherAgent:
    """Push the delivery branch and create a review request without an LLM loop."""

    def execute(self, work_order_id: str, context: dict[str, Any]) -> dict[str, Any]:
        workspace = Path(str(context.get("workspacePath") or ""))
        if not workspace.is_dir():
            raise PublisherCompletionError(f"workspace not found: {workspace}")

        delivery_branch = str(context.get("deliveryBranch") or "").strip()
        if not delivery_branch:
            raise PublisherCompletionError("delivery branch missing from publication context")

        integration_branch = str(context.get("integrationBranch") or "preprod").strip() or "preprod"
        project_key = str(context.get("projectKey") or "").strip().upper() or None
        provider = normalize_vcs_provider(context.get("vcs") or load_project_vcs_provider(project_key or ""))
        if provider != "github":
            raise PublisherCompletionError(
                f"Heuristic publisher supports GitHub only (project provider: {provider})"
            )

        mcp_config = resolve_project_mcp_server(project_key or "", "github")
        token = github_token_from_config(mcp_config or {})
        if not token:
            raise PublisherCompletionError("GitHub token missing from project MCP config")

        jira_key = str(
            context.get("jiraKey")
            or (context.get("workOrder") or {}).get("jiraKey")
            or work_order_id
        )

        repo_path = self._resolve_repo_path(context, project_key)
        existing_pr = find_existing_github_pull_request(
            token=token,
            repo_path=repo_path,
            head_branch=delivery_branch,
            base_branch=integration_branch,
        )
        if existing_pr:
            pr_url = str(existing_pr.get("html_url") or "")
            pr_number = existing_pr.get("number")
            if pr_url and isinstance(pr_number, int):
                logger.info(
                    "Reusing existing GitHub PR #%s for %s (skip push)",
                    pr_number,
                    delivery_branch,
                )
                completion = {
                    "reviewRequestUrl": pr_url,
                    "reviewRequestNumber": pr_number,
                    "reviewRequestProvider": "github",
                    "mrUrl": pr_url,
                    "mrIid": pr_number,
                    "targetBranch": integration_branch,
                    "status": "published",
                    "reusedExistingPullRequest": True,
                }
                draft_id = str(context.get("draftId") or "")
                if draft_id:
                    set_mr_draft_publication(
                        draft_id,
                        review_request_url=completion["reviewRequestUrl"],
                        review_request_number=completion["reviewRequestNumber"],
                        review_request_provider=completion["reviewRequestProvider"],
                    )
                return completion

        commit_message = f"{jira_key}: {str(context.get('mrTitle') or 'delivery work')}"
        commit_delivery_work(workspace, branch=delivery_branch, message=commit_message)
        push_delivery_branch(workspace, delivery_branch=delivery_branch)

        repo_path = self._resolve_repo_path(context, project_key)
        pr = create_github_pull_request(
            token=token,
            repo_path=repo_path,
            title=str(context.get("mrTitle") or f"{jira_key}: delivery"),
            body=str(context.get("mrDescription") or ""),
            head_branch=delivery_branch,
            base_branch=integration_branch,
        )
        pr_url = str(pr.get("html_url") or "")
        pr_number = pr.get("number")
        if not pr_url or not isinstance(pr_number, int):
            raise PublisherCompletionError("GitHub PR response missing html_url or number")

        completion = {
            "reviewRequestUrl": pr_url,
            "reviewRequestNumber": pr_number,
            "reviewRequestProvider": "github",
            "mrUrl": pr_url,
            "mrIid": pr_number,
            "targetBranch": integration_branch,
            "status": "published",
        }

        draft_id = str(context.get("draftId") or "")
        if draft_id:
            set_mr_draft_publication(
                draft_id,
                review_request_url=completion["reviewRequestUrl"],
                review_request_number=completion["reviewRequestNumber"],
                review_request_provider=completion["reviewRequestProvider"],
            )
        return completion

    @staticmethod
    def _resolve_repo_path(context: dict[str, Any], project_key: str | None) -> str:
        from delivery_runtime.readiness.project_mapping import load_project_mapping

        explicit = str(context.get("targetRepo") or "").strip()
        if explicit:
            return explicit if explicit.startswith("github.com/") else f"github.com/{explicit.strip('/')}"

        if project_key:
            mapping = load_project_mapping()
            entry = mapping.get(project_key) or mapping.get(project_key.lower()) or {}
            default_repo = str(entry.get("default_repo") or "").strip()
            if default_repo:
                return default_repo if default_repo.startswith("github.com/") else f"github.com/{default_repo.strip('/')}"

        raise PublisherCompletionError("Could not resolve GitHub repository path for publication")
