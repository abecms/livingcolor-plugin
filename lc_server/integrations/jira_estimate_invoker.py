"""MCP-backed Jira originalEstimate invoker (LivingColor Server integration layer)."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

_GET_TOOL_CANDIDATES = ("jira_get_issue", "get_issue", "getJiraIssue")
_UPDATE_TOOL_CANDIDATES = ("jira_update_issue", "update_issue", "editJiraIssue", "edit_issue")


class McpJiraEstimateInvoker:
    """Read and write Jira issue time tracking through the connected Jira MCP server.

    Implements the ``JiraEstimateInvoker`` protocol from
    ``delivery_runtime.jira.estimate_writeback``.
    """

    def get_issue(self, issue_key: str) -> dict[str, Any]:
        from hermes_cli.jira_dashboard import (
            JiraDashboardError,
            _extract_single_issue,
            _find_tool,
        )

        tool_names, invoke, cloud_id = self._connect()
        tool = _find_tool(tool_names, *_GET_TOOL_CANDIDATES)
        if not tool:
            raise RuntimeError("Connected Jira MCP server does not expose an issue read tool")

        # Mirror _issue_detail_arg_variants: snake_case servers (mcp-atlassian)
        # take issue_key + CSV fields; the official Atlassian server takes
        # issueIdOrKey (+ cloudId when resolved) with a fields list.
        arg_variants: list[dict[str, Any]] = [
            {"issue_key": issue_key, "fields": "timetracking"},
            {"issue_key": issue_key},
            {"issueIdOrKey": issue_key, "fields": ["timetracking"]},
            {"issueIdOrKey": issue_key},
            {"issueKey": issue_key},
        ]
        if cloud_id:
            arg_variants = [
                {**args, "cloudId": cloud_id} if "issueIdOrKey" in args else args
                for args in arg_variants
            ]

        last_error: Exception | None = None
        for args in arg_variants:
            try:
                payload = self._invoke_parsed(invoke, tool, args)
                issue = _extract_single_issue(payload)
                if issue:
                    return issue
            except JiraDashboardError as exc:
                last_error = exc
                logger.debug(
                    "Jira issue read failed for %s with args %s: %s",
                    issue_key,
                    sorted(args.keys()),
                    exc,
                )
        if last_error:
            raise RuntimeError(f"Could not read Jira issue {issue_key}: {last_error}") from last_error
        raise RuntimeError(f"Could not read Jira issue {issue_key}")

    def update_estimate(self, issue_key: str, estimate: str) -> None:
        from hermes_cli.jira_dashboard import JiraDashboardError, _find_tool

        tool_names, invoke, cloud_id = self._connect()
        tool = _find_tool(tool_names, *_UPDATE_TOOL_CANDIDATES)
        if not tool:
            raise RuntimeError("Connected Jira MCP server does not expose an issue update tool")

        fields = {"timetracking": {"originalEstimate": estimate}}
        arg_variants: list[dict[str, Any]] = [
            {"issue_key": issue_key, "fields": fields},
            {"issueIdOrKey": issue_key, "fields": fields},
            {"issueKey": issue_key, "fields": fields},
        ]
        if cloud_id:
            arg_variants = [
                {**args, "cloudId": cloud_id} if "issueIdOrKey" in args else args
                for args in arg_variants
            ]

        last_error: Exception | None = None
        for args in arg_variants:
            try:
                self._invoke_parsed(invoke, tool, args)
                return
            except JiraDashboardError as exc:
                last_error = exc
                logger.debug(
                    "Jira estimate update failed for %s with args %s: %s",
                    issue_key,
                    sorted(args.keys()),
                    exc,
                )
        raise RuntimeError(
            f"Could not update Jira originalEstimate for {issue_key}: {last_error}"
        ) from last_error

    @staticmethod
    def _connect() -> tuple[list[str], Callable[[str, dict], dict], str | None]:
        from lc_server.integrations.mcp_server_resolver import active_jira_mcp_name
        from hermes_cli.jira_dashboard import (
            JiraDashboardError,
            _ensure_cloud_id,
            ensure_jira_mcp_connected,
        )
        from hermes_cli.mcp_config import _get_mcp_servers
        from tools.mcp_tool import invoke_mcp_tool, list_connected_mcp_raw_tool_names

        try:
            ensure_jira_mcp_connected()
        except JiraDashboardError as exc:
            raise RuntimeError(str(exc)) from exc

        jira_name = active_jira_mcp_name()
        cfg = _get_mcp_servers().get(jira_name) or {}
        tool_names = list_connected_mcp_raw_tool_names(jira_name)

        def invoke(tool_name: str, arguments: dict) -> dict:
            return invoke_mcp_tool(jira_name, tool_name, arguments)

        try:
            cloud_id = _ensure_cloud_id(cfg, tool_names, invoke)
        except JiraDashboardError:
            cloud_id = None
        return tool_names, invoke, cloud_id

    @staticmethod
    def _invoke_parsed(invoke: Callable[[str, dict], dict], tool: str, args: dict) -> Any:
        from hermes_cli.jira_dashboard import _parse_tool_payload

        return _parse_tool_payload(invoke(tool, args))
