"""Jira issue fetch for readiness scanning (LivingColor Server integration layer)."""

from __future__ import annotations

import logging
from typing import Any

from delivery_runtime.readiness.errors import ReadinessIntegrationError

logger = logging.getLogger(__name__)

_READINESS_COMMENT_LIMIT = 50


def list_jira_projects_for_readiness(project_key: str) -> list[dict[str, str]]:
    """List Jira projects visible to the configured MCP server."""
    from lc_server.integrations.mcp_server_resolver import active_jira_mcp_name
    from hermes_cli.jira_dashboard import (
        JiraDashboardError,
        _fetch_projects,
        ensure_jira_mcp_connected,
    )
    from hermes_cli.mcp_config import _get_mcp_servers
    from tools.mcp_tool import invoke_mcp_tool, list_connected_mcp_raw_tool_names

    jira_name = active_jira_mcp_name()
    _get_mcp_servers().get(jira_name)
    try:
        ensure_jira_mcp_connected()
    except JiraDashboardError as exc:
        raise ReadinessIntegrationError(str(exc)) from exc

    tool_names = list_connected_mcp_raw_tool_names(jira_name)

    def invoke(tool_name: str, arguments: dict) -> dict:
        return invoke_mcp_tool(jira_name, tool_name, arguments)

    try:
        projects = _fetch_projects(tool_names, invoke)
    except JiraDashboardError as exc:
        raise ReadinessIntegrationError(str(exc)) from exc

    return [
        {"key": str(item.get("key") or "").strip(), "name": str(item.get("name") or item.get("key") or "").strip()}
        for item in projects
        if str(item.get("key") or "").strip()
    ]


def fetch_issues_for_readiness(project_key: str, *, max_results: int = 200) -> list[dict[str, Any]]:
    """Fetch and normalize Jira issues for readiness analysis."""
    from delivery_runtime.readiness.project_settings import resolve_jira_project_key
    from delivery_runtime.readiness.ticket_scope import (
        build_ticket_scope_jql_variants,
        load_ticket_scope_for_project,
    )

    livingcolor_project_key = str(project_key or "").strip().upper()
    jira_project_key = resolve_jira_project_key(livingcolor_project_key)
    ticket_scope = load_ticket_scope_for_project(livingcolor_project_key)
    from lc_server.integrations.mcp_server_resolver import active_jira_mcp_name
    from hermes_cli.jira_dashboard import (
        JiraDashboardError,
        _ensure_cloud_id,
        _fetch_projects,
        _issue_field,
        _issue_jql_variants,
        _normalize_issue,
        _resolve_project_key,
        _search_issues_with_fallbacks,
        ensure_jira_mcp_connected,
    )
    from hermes_cli.mcp_config import _get_mcp_servers
    from tools.mcp_tool import invoke_mcp_tool, list_connected_mcp_raw_tool_names

    try:
        ensure_jira_mcp_connected()
    except JiraDashboardError as exc:
        raise ReadinessIntegrationError(str(exc)) from exc

    jira_name = active_jira_mcp_name()
    cfg = _get_mcp_servers().get(jira_name)
    tool_names = list_connected_mcp_raw_tool_names(jira_name)

    def invoke(tool_name: str, arguments: dict) -> dict:
        return invoke_mcp_tool(jira_name, tool_name, arguments)

    try:
        projects = _fetch_projects(tool_names, invoke)
        selected_project = _resolve_project_key(projects, jira_project_key)
        if not selected_project:
            raise ReadinessIntegrationError(f"Unknown Jira project key: {jira_project_key}")

        cloud_id = _ensure_cloud_id(cfg, tool_names, invoke)
        jql_variants = build_ticket_scope_jql_variants(selected_project, ticket_scope)
        raw_issues = _search_issues_with_fallbacks(
            tool_names,
            invoke,
            cloud_id=cloud_id,
            jql_variants=jql_variants,
            max_results=max_results,
        )
    except JiraDashboardError as exc:
        raise ReadinessIntegrationError(str(exc)) from exc

    snapshots: list[dict[str, Any]] = []
    for raw in raw_issues:
        normalized = _normalize_issue(raw)
        snapshots.append(enrich_issue_snapshot(raw, normalized, livingcolor_project_key))
    return snapshots


def fetch_issue_snapshot_for_readiness(jira_key: str) -> dict[str, Any]:
    """Fetch a single Jira issue with comments for readiness re-analysis."""
    from lc_server.integrations.mcp_server_resolver import active_jira_mcp_name
    from hermes_cli.jira_dashboard import (
        JiraDashboardError,
        _extract_single_issue,
        _find_issue_detail_tool,
        _issue_detail_arg_variants,
        _normalize_issue,
        _parse_tool_payload,
        ensure_jira_mcp_connected,
    )
    from hermes_cli.mcp_config import _get_mcp_servers
    from tools.mcp_tool import invoke_mcp_tool, list_connected_mcp_raw_tool_names

    safe_key = str(jira_key or "").strip()
    if not safe_key:
        raise ReadinessIntegrationError("Jira issue key is required")

    try:
        ensure_jira_mcp_connected()
    except JiraDashboardError as exc:
        raise ReadinessIntegrationError(str(exc)) from exc

    jira_name = active_jira_mcp_name()
    _get_mcp_servers().get(jira_name)
    tool_names = list_connected_mcp_raw_tool_names(jira_name)

    def invoke(tool_name: str, arguments: dict) -> dict:
        return invoke_mcp_tool(jira_name, tool_name, arguments)

    detail_tool = _find_issue_detail_tool(tool_names)
    if not detail_tool:
        raise ReadinessIntegrationError("Jira issue detail tool is not available")

    project_key = safe_key.split("-")[0].strip().upper()
    last_error: Exception | None = None
    for args in _issue_detail_arg_variants(
        detail_tool,
        safe_key,
        include_comments=True,
        comment_limit=_READINESS_COMMENT_LIMIT,
    ):
        try:
            payload = _parse_tool_payload(invoke(detail_tool, args))
            detail = _extract_single_issue(payload)
            if not detail:
                continue
            normalized = _normalize_issue(detail)
            snapshot = enrich_issue_snapshot(detail, normalized, project_key)
            attach_issue_comments(snapshot, detail)
            from lc_server.integrations.jira_attachment_extract import (
                enrich_snapshot_with_attachment_extracts,
            )

            return enrich_snapshot_with_attachment_extracts(snapshot)
        except JiraDashboardError as exc:
            last_error = exc
            logger.debug(
                "Jira issue detail failed for %s with args %s: %s",
                safe_key,
                sorted(args.keys()),
                exc,
            )

    message = f"Could not fetch Jira issue {safe_key} for readiness re-analysis"
    if last_error:
        raise ReadinessIntegrationError(f"{message}: {last_error}") from last_error
    raise ReadinessIntegrationError(message)


def extract_issue_comments(raw_issue: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Jira issue comments into analyst-friendly records."""
    from hermes_cli.jira_dashboard import _issue_field, _issue_text_field

    fields = raw_issue.get("fields") if isinstance(raw_issue.get("fields"), dict) else raw_issue
    if not isinstance(fields, dict):
        return []

    comment_container = fields.get("comment")
    raw_comments: list[Any] = []
    if isinstance(comment_container, dict):
        nested = comment_container.get("comments")
        if isinstance(nested, list):
            raw_comments = nested
    elif isinstance(comment_container, list):
        raw_comments = comment_container

    comments: list[dict[str, Any]] = []
    for item in raw_comments:
        if not isinstance(item, dict):
            continue
        body = _issue_text_field({"fields": {"body": item.get("body")}}, "body")
        if not body.strip():
            continue
        comments.append(
            {
                "author": _issue_field(item, "author") or None,
                "body": body.strip(),
                "created": str(item.get("created") or item.get("updated") or "").strip() or None,
            }
        )
    return comments[-_READINESS_COMMENT_LIMIT:]


def attach_issue_comments(snapshot: dict[str, Any], raw_issue: dict[str, Any]) -> dict[str, Any]:
    """Attach normalized comments and reopened context to a readiness snapshot."""
    comments = extract_issue_comments(raw_issue)
    snapshot["comments"] = comments
    snapshot["commentCount"] = len(comments)
    snapshot["isReopened"] = snapshot_is_reopened(snapshot, comments)
    return snapshot


def snapshot_is_reopened(snapshot: dict[str, Any], comments: list[dict[str, Any]] | None = None) -> bool:
    """Heuristic: ticket was reopened or feedback in comments supersedes the original scope."""
    status = str(snapshot.get("status") or "").lower()
    labels = [str(label).lower() for label in snapshot.get("labels") or [] if str(label).strip()]
    if "reopen" in status or any("reopen" in label for label in labels):
        return True

    for comment in comments or snapshot.get("comments") or []:
        if not isinstance(comment, dict):
            continue
        body = str(comment.get("body") or "").lower()
        if any(token in body for token in ("reopened", "re-opened", "re open", "back to dev", "sent back")):
            return True
    return False


def enrich_issue_snapshot(raw: dict[str, Any], normalized: dict[str, Any], project_key: str) -> dict[str, Any]:
    from hermes_cli.jira_dashboard import _issue_field

    snapshot = dict(normalized)
    snapshot["projectKey"] = project_key
    snapshot["issueType"] = _issue_field(raw, "issuetype", "issueType")
    snapshot["statusCategory"] = _issue_status_category(raw)
    fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else raw
    labels = fields.get("labels") if isinstance(fields, dict) else []
    snapshot["labels"] = [str(label) for label in labels] if isinstance(labels, list) else []
    assignee_raw = fields.get("assignee") if isinstance(fields, dict) else None
    if isinstance(assignee_raw, dict):
        display_name = str(
            assignee_raw.get("displayName") or assignee_raw.get("display_name") or ""
        ).strip()
        email = str(assignee_raw.get("emailAddress") or assignee_raw.get("email") or "").strip()
        if display_name:
            snapshot["assigneeDisplayName"] = display_name
            snapshot["assignee"] = display_name
        if email:
            snapshot["assigneeEmail"] = email
    comments = extract_issue_comments(raw)
    if comments:
        snapshot["comments"] = comments
        snapshot["commentCount"] = len(comments)
        snapshot["isReopened"] = snapshot_is_reopened(snapshot, comments)
    return snapshot


def _issue_status_category(raw: dict[str, Any]) -> str:
    fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else raw
    if not isinstance(fields, dict):
        return ""

    status = fields.get("status")
    if isinstance(status, dict):
        category = status.get("statusCategory")
        if isinstance(category, dict):
            for key in ("name", "key"):
                value = category.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        elif isinstance(category, str) and category.strip():
            return category.strip()

    top_level = fields.get("statusCategory")
    if isinstance(top_level, dict):
        for key in ("name", "key"):
            value = top_level.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    elif isinstance(top_level, str) and top_level.strip():
        return top_level.strip()

    return ""
