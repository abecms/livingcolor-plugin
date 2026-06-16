"""MCP-backed Jira comment + transition invoker for delivery completion."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

_ADD_COMMENT_TOOLS = ("jira_add_comment", "add_comment", "addComment")
_GET_TRANSITIONS_TOOLS = ("jira_get_transitions", "get_transitions", "getTransitions")
_TRANSITION_TOOLS = ("jira_transition_issue", "transition_issue", "transitionIssue")


class McpJiraDeliveryInvoker:
    """Post delivery comments and transition issues through the Jira MCP server."""

    def add_comment(self, issue_key: str, body: str) -> dict[str, Any]:
        from hermes_cli.jira_dashboard import JiraDashboardError, _find_tool

        tool_names, invoke, _cloud_id = self._connect()
        tool = _find_tool(tool_names, *_ADD_COMMENT_TOOLS)
        if not tool:
            raise RuntimeError("Connected Jira MCP server does not expose a comment tool")

        text = body.strip()
        if not text:
            raise ValueError("Jira comment body is required")

        arg_variants: list[dict[str, Any]] = [
            {"issue_key": issue_key, "body": text},
            {"issueIdOrKey": issue_key, "body": text},
            {"issueKey": issue_key, "body": text},
            {"issue_key": issue_key, "comment": text},
        ]
        last_error: Exception | None = None
        for args in arg_variants:
            try:
                return self._invoke_parsed(invoke, tool, args)
            except JiraDashboardError as exc:
                last_error = exc
                logger.debug(
                    "Jira add_comment failed for %s with args %s: %s",
                    issue_key,
                    sorted(args.keys()),
                    exc,
                )
        raise RuntimeError(f"Could not add Jira comment on {issue_key}: {last_error}") from last_error

    def list_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        from hermes_cli.jira_dashboard import JiraDashboardError, _find_tool

        tool_names, invoke, _cloud_id = self._connect()
        tool = _find_tool(tool_names, *_GET_TRANSITIONS_TOOLS)
        if not tool:
            raise RuntimeError("Connected Jira MCP server does not expose a transitions tool")

        arg_variants: list[dict[str, Any]] = [
            {"issue_key": issue_key},
            {"issueIdOrKey": issue_key},
            {"issueKey": issue_key},
        ]
        last_error: Exception | None = None
        for args in arg_variants:
            try:
                payload = self._invoke_parsed(invoke, tool, args)
                return _normalize_transitions(payload)
            except JiraDashboardError as exc:
                last_error = exc
        raise RuntimeError(
            f"Could not list Jira transitions for {issue_key}: {last_error}"
        ) from last_error

    def transition_issue(self, issue_key: str, *, transition_id: str) -> dict[str, Any]:
        from hermes_cli.jira_dashboard import JiraDashboardError, _find_tool

        tool_names, invoke, _cloud_id = self._connect()
        tool = _find_tool(tool_names, *_TRANSITION_TOOLS)
        if not tool:
            raise RuntimeError("Connected Jira MCP server does not expose a transition tool")

        transition_id = str(transition_id).strip()
        arg_variants: list[dict[str, Any]] = [
            {"issue_key": issue_key, "transition_id": transition_id},
            {"issue_key": issue_key, "transitionId": transition_id},
            {"issueIdOrKey": issue_key, "transitionId": transition_id},
            {"issueKey": issue_key, "transition_id": transition_id},
        ]
        last_error: Exception | None = None
        for args in arg_variants:
            try:
                return self._invoke_parsed(invoke, tool, args)
            except JiraDashboardError as exc:
                last_error = exc
        raise RuntimeError(
            f"Could not transition Jira issue {issue_key}: {last_error}"
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


def _normalize_transitions(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        nested = payload.get("transitions") or payload.get("values")
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
        if "result" in payload and isinstance(payload["result"], str):
            try:
                parsed = json.loads(payload["result"])
            except json.JSONDecodeError:
                return []
            return _normalize_transitions(parsed)
    if isinstance(payload, str):
        try:
            return _normalize_transitions(json.loads(payload))
        except json.JSONDecodeError:
            return []
    return []


def _normalize_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().strip())


def pick_transition_id(
    transitions: list[dict[str, Any]],
    *,
    preferred_names: list[str],
) -> str | None:
    """Pick the first transition whose name matches a preferred label."""
    by_name = {
        _normalize_label(str(item.get("name") or "")): str(item.get("id") or "")
        for item in transitions
        if item.get("id") is not None
    }
    for preferred in preferred_names:
        normalized = _normalize_label(preferred)
        if not normalized:
            continue
        if normalized in by_name and by_name[normalized]:
            return by_name[normalized]
        for name, transition_id in by_name.items():
            if normalized in name or name in normalized:
                return transition_id
    return None
