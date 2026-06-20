"""Deterministic GitHub/GitLab publication for cloud validation runs."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from delivery_runtime.development.git_branch import commit_delivery_work
from delivery_runtime.shadow.context import allow_internal_git
from lc_server.agent_bridge.hermes_publisher import PublisherCompletionError, parse_publisher_completion
from lc_server.integrations.vcs.provider import normalize_vcs_provider

logger = logging.getLogger(__name__)


class HeuristicPublisherAgent:
    """Push the delivery branch and create a review request without an LLM loop."""

    def execute(self, work_order_id: str, context: dict[str, Any]) -> dict[str, Any]:
        workspace = Path(str(context.get("workspacePath") or ""))
        if not workspace.is_dir():
            raise PublisherCompletionError(f"workspace not found: {workspace}")

        delivery_branch = str(context.get("deliveryBranch") or "")
        if not delivery_branch:
            raise PublisherCompletionError("delivery branch missing from publication context")

        integration_branch = str(context.get("integrationBranch") or "").strip()
        if not integration_branch:
            raise PublisherCompletionError("integration branch missing from publication context")

        jira_key = str(
            context.get("jiraKey")
            or (context.get("workOrder") or {}).get("jiraKey")
            or work_order_id
        )
        mr_title = str(context.get("mrTitle") or f"{jira_key}: delivery work")
        mr_description = str(context.get("mrDescription") or "")
        commit_message = f"{jira_key}: {mr_title}"
        commit_delivery_work(workspace, branch=delivery_branch, message=commit_message)

        project_key = str(context.get("projectKey") or "").strip().upper() or None
        provider = normalize_vcs_provider(
            context.get("vcs") or context.get("reviewRequestProvider") or "github"
        )
        if provider != "github":
            raise PublisherCompletionError(
                f"Heuristic publisher supports GitHub only (got {provider!r})"
            )

        from delivery_runtime.readiness.project_settings import resolve_project_mcp_server
        from lc_server.integrations.vcs.github import (
            build_github_clone_url,
            create_pull_request,
            github_token_from_config,
        )

        mcp_config = resolve_project_mcp_server(project_key or "", "github")
        token = github_token_from_config(mcp_config)
        if not token:
            raise PublisherCompletionError("No GitHub token configured for publication")

        repo_id = str(context.get("targetRepo") or context.get("repoId") or "").strip()
        if not repo_id:
            approved_plan = context.get("approvedAnalysisPlan") or context.get("approvedPlanRef") or {}
            if isinstance(approved_plan, dict):
                repo_id = str(approved_plan.get("targetRepo") or "").strip()
        if not repo_id and project_key:
            from delivery_runtime.readiness.project_mapping import load_project_mapping_entry

            entry = load_project_mapping_entry(project_key)
            repo_id = str(entry.get("default_repo") or "").strip()
        repo_path = repo_id.removeprefix("github.com/").strip("/")
        if not repo_path:
            raise PublisherCompletionError("target repository missing from publication context")

        push_url = build_github_clone_url(f"github.com/{repo_path}", token)
        self._push_branch(workspace, delivery_branch, push_url)

        pr = create_pull_request(
            mcp_config=mcp_config,
            repo_path=repo_path,
            title=mr_title,
            body=mr_description,
            head=delivery_branch,
            base=integration_branch,
        )
        pr_number = int(pr.get("number") or 0)
        pr_url = str(pr.get("html_url") or "")
        if not pr_number or not pr_url:
            raise PublisherCompletionError("GitHub PR creation returned incomplete payload")

        completion = {
            "reviewRequestUrl": pr_url,
            "reviewRequestNumber": pr_number,
            "reviewRequestProvider": "github",
            "mrUrl": pr_url,
            "mrIid": pr_number,
            "targetBranch": integration_branch,
            "status": "published",
        }
        return parse_publisher_completion(
            '{"status": "published", "reviewRequestUrl": "%s", "reviewRequestNumber": %d, '
            '"targetBranch": "%s", "provider": "github"}'
            % (pr_url, pr_number, integration_branch)
        )

    @staticmethod
    def _push_branch(workspace: Path, branch: str, push_url: str) -> None:
        with allow_internal_git():
            set_remote = subprocess.run(
                ["git", "remote", "set-url", "origin", push_url],
                cwd=workspace,
                check=False,
                capture_output=True,
                text=True,
            )
            if set_remote.returncode != 0:
                add_remote = subprocess.run(
                    ["git", "remote", "add", "origin", push_url],
                    cwd=workspace,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if add_remote.returncode != 0:
                    stderr = (add_remote.stderr or add_remote.stdout or "").strip()
                    raise PublisherCompletionError(f"git remote setup failed: {stderr}")

            checkout = subprocess.run(
                ["git", "checkout", "-B", branch],
                cwd=workspace,
                check=False,
                capture_output=True,
                text=True,
            )
            if checkout.returncode != 0:
                stderr = (checkout.stderr or checkout.stdout or "").strip()
                raise PublisherCompletionError(f"git checkout failed: {stderr}")

            push = subprocess.run(
                ["git", "push", "-u", "origin", branch],
                cwd=workspace,
                check=False,
                capture_output=True,
                text=True,
            )
        if push.returncode != 0:
            stderr = (push.stderr or push.stdout or "").strip()
            raise PublisherCompletionError(f"git push failed: {stderr}")
