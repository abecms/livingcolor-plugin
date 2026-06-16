"""
Jira dashboard helpers for the LivingColor desktop app.

Connects to the Atlassian Rovo MCP server, fetches live Jira signals via MCP
tools, and returns a structured payload for the project dashboard UI.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import base64
import mimetypes
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from hermes_cli.mcp_config import _get_mcp_servers, _oauth_tokens_present, _save_mcp_server

logger = logging.getLogger(__name__)

JIRA_MCP_NAME = "jira"
JIRA_MCP_URL = "https://mcp.atlassian.com/v1/mcp/authv2"
JIRA_MCP_CONFIG: Dict[str, Any] = {
    "command": "npx",
    "args": ["-y", "mcp-remote@latest", JIRA_MCP_URL],
    "connect_timeout": 300,
}


def _active_jira_mcp_name() -> str:
    from lc_server.integrations.mcp_server_resolver import resolve_jira_mcp_server_name

    return resolve_jira_mcp_server_name() or JIRA_MCP_NAME


class JiraDashboardError(Exception):
    """Raised when Jira dashboard data cannot be fetched."""


def ensure_jira_mcp_config() -> dict:
    """Ensure the Jira MCP preset exists in config.yaml."""
    servers = _get_mcp_servers()
    existing = servers.get(JIRA_MCP_NAME)
    if existing:
        if _uses_env_auth(existing):
            return dict(existing)
        merged = {**JIRA_MCP_CONFIG, **existing}
        if merged != existing:
            _save_mcp_server(JIRA_MCP_NAME, merged)
        return merged
    _save_mcp_server(JIRA_MCP_NAME, dict(JIRA_MCP_CONFIG))
    return dict(JIRA_MCP_CONFIG)


def _jira_server_connected() -> bool:
    from tools.mcp_tool import get_mcp_status

    active_name = _active_jira_mcp_name()
    for entry in get_mcp_status():
        if entry.get("name") == active_name and entry.get("connected"):
            return True
    return False


def connect_jira_mcp() -> dict:
    """Connect the configured Jira MCP server via the MCP runtime."""
    from lc_server.integrations.mcp_server_resolver import resolve_jira_mcp_server_name
    from tools.mcp_tool import list_connected_mcp_tool_names, reconnect_mcp_server

    resolved = resolve_jira_mcp_server_name()
    if resolved:
        cfg = dict(_get_mcp_servers().get(resolved) or {})
        name = resolved
    else:
        cfg = ensure_jira_mcp_config()
        name = JIRA_MCP_NAME

    reconnect_mcp_server(name, cfg)
    connected = _jira_server_connected()
    oauth_ready = _oauth_tokens_present(name) if cfg.get("auth") == "oauth" else True
    tool_count = 0
    if connected:
        tool_count = len(list_connected_mcp_tool_names(name))

    status = "connected" if connected and oauth_ready else "disconnected"
    message = "Connected to Jira via MCP."
    if not connected:
        message = (
            "Could not connect to Jira. Complete the browser OAuth flow if prompted, "
            "then try again."
        )
    elif cfg.get("auth") == "oauth" and not oauth_ready:
        message = "Jira MCP connected, but OAuth tokens were not saved. Retry the login flow."
        status = "disconnected"

    return {
        "ok": connected and oauth_ready,
        "status": status,
        "message": message,
        "authenticated": connected and oauth_ready,
        "toolCount": tool_count,
    }


def ensure_jira_mcp_connected() -> None:
    """Ensure Jira MCP is connected in the current process (reconnect when needed).

    Saved credentials or MCP config alone are not enough: the LivingColor backend
    must hold an active MCP session before tools such as daily analysis can run.
    """
    cfg = _get_mcp_servers().get(_active_jira_mcp_name())
    if not cfg:
        raise JiraDashboardError("Jira MCP is not configured. Connect Jira before scanning.")

    from tools.mcp_tool import list_connected_mcp_raw_tool_names

    active_name = _active_jira_mcp_name()
    if _jira_server_connected() and list_connected_mcp_raw_tool_names(active_name):
        return

    result = connect_jira_mcp()
    if not result.get("ok"):
        message = str(result.get("message") or "Jira is not connected. Connect Jira before scanning.")
        raise JiraDashboardError(message)

    if not list_connected_mcp_raw_tool_names(active_name):
        raise JiraDashboardError("Jira MCP is connected but no tools are available.")


def _find_tool(tool_names: List[str], *candidates: str) -> Optional[str]:
    by_lower = {name.lower(): name for name in tool_names}
    for candidate in candidates:
        key = candidate.lower()
        if key in by_lower:
            return by_lower[key]
    for candidate in candidates:
        needle = candidate.lower()
        for name in tool_names:
            if needle in name.lower():
                return name
    return None


def _parse_mcp_json_payload(parsed: dict) -> Any:
    """Parse MCP tool output, preferring JSON in the result field."""
    if parsed.get("error"):
        raise JiraDashboardError(str(parsed["error"]))

    result = parsed.get("result", parsed)
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result
    return result


def _parse_tool_payload(parsed: dict) -> Any:
    if parsed.get("error"):
        raise JiraDashboardError(str(parsed["error"]))

    structured = parsed.get("structuredContent")
    result = parsed.get("result", parsed)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            pass

    if structured is not None:
        if isinstance(structured, dict) and _extract_issues(structured):
            return structured
        if isinstance(result, dict) and _extract_issues(result):
            return result
        if isinstance(result, list) and result:
            return result
        if isinstance(structured, dict) and structured:
            return structured
        if isinstance(result, dict) and result:
            return result
        if isinstance(result, list):
            return result
        return structured

    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result
    return result


def _walk_strings(node: Any) -> List[str]:
    out: List[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for value in node.values():
            out.extend(_walk_strings(value))
    elif isinstance(node, list):
        for item in node:
            out.extend(_walk_strings(item))
    return out


def _extract_cloud_id(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        for key in ("cloudId", "cloud_id", "id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for key in ("url", "siteUrl", "site_url"):
            value = payload.get(key)
            if isinstance(value, str) and "atlassian.net" in value:
                return value.strip()
        for key in ("resources", "sites", "clouds", "values", "nodes"):
            items = payload.get(key)
            if isinstance(items, list):
                for item in items:
                    cloud_id = _extract_cloud_id(item)
                    if cloud_id:
                        return cloud_id
    elif isinstance(payload, list):
        for item in payload:
            cloud_id = _extract_cloud_id(item)
            if cloud_id:
                return cloud_id
    return None


def _extract_issues(payload: Any) -> List[dict]:
    if isinstance(payload, dict):
        for key in ("issues", "nodes", "values", "results"):
            items = payload.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        nested = payload.get("issues")
        if isinstance(nested, dict):
            nodes = nested.get("nodes")
            if isinstance(nodes, list):
                return [item for item in nodes if isinstance(item, dict)]
    elif isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _issue_field(issue: dict, *paths: str) -> str:
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else issue
    for path in paths:
        value = fields.get(path) if isinstance(fields, dict) else issue.get(path)
        if isinstance(value, dict):
            for nested in ("displayName", "display_name", "name", "value", "key"):
                inner = value.get(nested)
                if isinstance(inner, str) and inner.strip():
                    return inner.strip()
        elif isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _issue_text_field(issue: dict, path: str) -> str:
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else issue
    value = fields.get(path) if isinstance(fields, dict) else issue.get(path)
    if isinstance(value, str):
        return " ".join(value.split())

    parts: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            text = node.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return " ".join(" ".join(parts).split())


def _issue_url(issue: dict) -> str:
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
    for source in (issue, fields):
        if not isinstance(source, dict):
            continue
        for key in ("browseUrl", "browse_url", "webUrl", "web_url", "url", "self"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _issue_attachments(issue: dict, issue_key: str = "") -> List[dict]:
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else issue
    raw = fields.get("attachment") if isinstance(fields, dict) else None
    if raw is None and isinstance(fields, dict):
        raw = fields.get("attachments")

    if isinstance(raw, dict):
        for key in ("values", "nodes", "results", "attachments"):
            value = raw.get(key)
            if isinstance(value, list):
                raw = value
                break

    if not isinstance(raw, list):
        return []

    attachments: List[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = _first_string(item, "filename", "fileName", "name", "title")
        url = _first_string(item, "content", "url", "downloadUrl", "download_url", "self")
        attachment_id = _first_string(item, "id", "attachmentId", "attachment_id")
        if not name and not url:
            continue
        attachments.append(
            {
                "id": attachment_id,
                "name": name or url,
                "mimeType": _first_string(item, "mimeType", "mime_type", "contentType", "content_type"),
                "url": url,
                "thumbnailUrl": _first_string(item, "thumbnail", "thumbnailUrl", "thumbnail_url"),
                "previewUrl": _jira_attachment_preview_url(
                    url,
                    issue_key=issue_key,
                    attachment_id=attachment_id,
                    name=name or url,
                ),
            }
        )
    return attachments


def _jira_attachment_preview_url(
    url: str,
    *,
    issue_key: str = "",
    attachment_id: str = "",
    name: str = "",
) -> str:
    safe_url = str(url or "").strip()
    safe_issue_key = str(issue_key or "").strip()
    if not safe_url and not safe_issue_key:
        return ""
    params = {}
    if safe_url:
        params["url"] = safe_url
    if safe_issue_key:
        params["issue_key"] = safe_issue_key
    if attachment_id:
        params["attachment_id"] = str(attachment_id).strip()
    if name:
        params["name"] = str(name).strip()
    return f"/api/jira/attachments/preview?{urllib.parse.urlencode(params)}"


def _first_string(source: dict, *keys: str) -> str:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value).strip()
            if text:
                return text
    return ""


def _normalize_issue(issue: dict) -> dict:
    key = _issue_field(issue, "key") or str(issue.get("key") or "").strip()
    summary = _issue_field(issue, "summary", "title")
    status = _issue_field(issue, "status", "statusCategory")
    assignee = _issue_field(issue, "assignee")
    priority = _issue_field(issue, "priority")
    description = _issue_text_field(issue, "description")
    url = _issue_url(issue)
    attachments = _issue_attachments(issue, issue_key=key)
    return {
        "key": key or "Issue",
        "summary": summary or "Untitled issue",
        "status": status or "Unknown",
        "assignee": assignee or "Unassigned",
        "priority": priority or "",
        "description": description,
        "url": url,
        "attachments": attachments,
    }


def _metric(label: str, value: str, detail: str, tone: str) -> dict:
    return {"label": label, "value": value, "detail": detail, "tone": tone}


def _sample_dashboard() -> dict:
    return {
        "connection": {
            "status": "disconnected",
            "message": "Connect Jira to replace sample data with live priorities and blockers.",
            "authenticated": False,
            "toolCount": 0,
        },
        "sampleData": True,
        "metrics": [
            _metric(
                "Delivery confidence",
                "82%",
                "Sample indicator — connect Jira for live delivery signals.",
                "good",
            ),
            _metric(
                "Sprint health",
                "Watch",
                "Two priorities need clarification before they move forward.",
                "warning",
            ),
            _metric(
                "Jira status",
                "Ready to connect",
                "Use Connect Jira to sign in through Atlassian MCP.",
                "neutral",
            ),
        ],
        "priorities": [],
        "blockers": [],
        "risks": [
            {
                "label": "Jira not connected",
                "detail": "Use the sample data for orientation until Jira is connected.",
            },
            {
                "label": "Unclear ownership",
                "detail": "Make sure every priority has one accountable owner before it moves forward.",
            },
        ],
        "actions": [
            "Review open priorities and identify blockers",
            "Turn the next product goal into clear Jira tickets",
            "Prepare a VisualQ update for stakeholders",
            "Summarize risks, owners, and next actions",
        ],
        "projects": [],
        "selectedProjectKey": None,
        "workspace": None,
        "pmInbox": [],
        "workspaceMaturity": {
            "level": "new",
            "confidence": 0.0,
            "reasons": ["Jira is not connected yet"],
        },
        "reportsReady": [],
    }


def _uses_env_auth(cfg: dict) -> bool:
    """Return True when Jira credentials are supplied via MCP env vars."""
    env = cfg.get("env") or {}
    if not isinstance(env, dict):
        return False
    return bool(
        str(env.get("JIRA_URL") or "").strip()
        and str(env.get("JIRA_USERNAME") or "").strip()
        and str(env.get("JIRA_API_TOKEN") or "").strip()
    )


def _uses_mcp_atlassian(cfg: dict) -> bool:
    """Return True when the preset targets the mcp-atlassian stdio server."""
    if _uses_env_auth(cfg):
        return True
    args = cfg.get("args") or []
    if isinstance(args, list):
        for arg in args:
            if "mcp-atlassian" in str(arg):
                return True
    command = str(cfg.get("command") or "")
    return "mcp-atlassian" in command


def _uses_header_auth(cfg: dict) -> bool:
    """Return True when the MCP server uses API token / header authentication."""
    headers = cfg.get("headers") or {}
    if not isinstance(headers, dict):
        return False
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if key.lower() != "authorization":
            continue
        lowered = value.strip().lower()
        if lowered.startswith("basic ") or lowered.startswith("bearer "):
            return True
    return False


def _ensure_cloud_id(
    cfg: dict,
    tool_names: List[str],
    invoke: Callable[[str, dict], dict],
) -> Optional[str]:
    """Resolve Jira cloudId; required for Rovo MCP API token auth only."""
    if _uses_mcp_atlassian(cfg):
        return None
    cloud_id = _resolve_cloud_id(tool_names, invoke)
    if cloud_id:
        return cloud_id
    if _uses_header_auth(cfg):
        raise JiraDashboardError(
            "Could not resolve your Jira cloudId. Recreate the API token with MCP scopes "
            "(including read:account), then connect again."
        )
    return None


_DASHBOARD_ISSUE_PAGE_SIZE = 100
# Keep open work plus Done issues resolved in the last ~month; drop older closed tickets.
_ISSUE_VISIBILITY_FILTER = "(statusCategory != Done OR resolutiondate >= -30d)"
_DASHBOARD_ISSUE_FIELDS = [
    "summary",
    "description",
    "attachment",
    "status",
    "assignee",
    "priority",
    "resolutiondate",
    "updated",
    "created",
]
_DASHBOARD_ISSUE_FIELDS_CSV = ",".join(_DASHBOARD_ISSUE_FIELDS)
def _project_scope_clause(project_key: Optional[str]) -> str:
    if not project_key:
        return _ISSUE_VISIBILITY_FILTER
    safe_key = str(project_key).replace('"', '\\"').strip()
    if not safe_key:
        return _ISSUE_VISIBILITY_FILTER
    return f'project = "{safe_key}" AND {_ISSUE_VISIBILITY_FILTER}'


_READINESS_ISSUE_FILTER = 'statusCategory = "To Do"'


def _readiness_project_scope_clause(project_key: Optional[str]) -> str:
    if not project_key:
        return _READINESS_ISSUE_FILTER
    safe_key = str(project_key).replace('"', '\\"').strip()
    if not safe_key:
        return _READINESS_ISSUE_FILTER
    return f'project = "{safe_key}" AND {_READINESS_ISSUE_FILTER}'


def _issue_jql_variants(project_key: Optional[str]) -> tuple[str, ...]:
    """All in-scope issues for a project (any assignee/status except stale Done)."""
    scope = _project_scope_clause(project_key)
    return (
        f"{scope} ORDER BY updated DESC",
        f"{scope} ORDER BY created DESC",
    )


def _readiness_issue_jql_variants(project_key: Optional[str]) -> tuple[str, ...]:
    """Only To Do tickets for daily readiness / BN analysis."""
    scope = _readiness_project_scope_clause(project_key)
    return (
        f"{scope} ORDER BY updated DESC",
        f"{scope} ORDER BY created DESC",
    )


def _blocker_jql_variants(project_key: Optional[str]) -> tuple[str, ...]:
    scope = _project_scope_clause(project_key)
    return (
        f'{scope} AND status = Blocked ORDER BY updated DESC',
        f'{scope} AND priority in (Highest) ORDER BY updated DESC',
    )


def _extract_projects(payload: Any) -> List[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if payload.get("key") and (payload.get("name") or payload.get("id")):
            return [payload]
        for key in ("projects", "values", "nodes", "results", "data"):
            items = payload.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    return []


def _normalize_project(project: dict) -> dict:
    key = _issue_field(project, "key") or str(project.get("key") or "").strip()
    name = _issue_field(project, "name") or str(project.get("name") or "").strip()
    if not key:
        return {}
    return {"key": key, "name": name or key}


def _find_projects_list_tool(tool_names: List[str]) -> Optional[str]:
    found = _find_tool(
        tool_names,
        "jira_get_all_projects",
        "get_all_projects",
        "getAllProjects",
        "listProjects",
        "getVisibleJiraProjects",
    )
    if found:
        return found
    for name in tool_names:
        lowered = name.lower()
        if "project" in lowered and ("all" in lowered or "list" in lowered or "visible" in lowered):
            return name
    return None


def _fetch_projects(
    tool_names: List[str],
    invoke: Callable[[str, dict], dict],
) -> List[dict]:
    list_tool = _find_projects_list_tool(tool_names)
    if not list_tool:
        logger.warning("Jira project list tool not found among MCP tools: %s", tool_names)
        return []

    payload: Any = None
    for args in ({"include_archived": False}, {}):
        try:
            payload = _parse_mcp_json_payload(invoke(list_tool, args))
            if payload:
                break
        except JiraDashboardError as exc:
            logger.warning("Jira project list failed (%s): %s", args, exc)

    if payload is None:
        return []

    if isinstance(payload, dict) and payload.get("success") is False:
        logger.warning(
            "Jira project list returned error: %s",
            payload.get("error") or payload,
        )
        return []

    projects = [_normalize_project(item) for item in _extract_projects(payload)]
    deduped: List[dict] = []
    seen: set[str] = set()
    for project in projects:
        key = project.get("key")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(project)
    deduped.sort(key=lambda item: str(item.get("name") or item.get("key")).lower())
    return deduped


def _resolve_project_key(
    projects: List[dict],
    requested: Optional[str],
) -> Optional[str]:
    if not projects:
        return requested.strip() if requested and requested.strip() else None
    keys = {str(p.get("key") or "") for p in projects}
    if requested and requested.strip() in keys:
        return requested.strip()
    return str(projects[0].get("key") or "") or None


def _workspace_from_project(project_key: Optional[str], projects: List[dict]) -> Optional[dict]:
    if not project_key:
        return None
    project = next((item for item in projects if item.get("key") == project_key), None)
    project_name = str((project or {}).get("name") or project_key).strip()
    return {
        "key": project_key,
        "name": f"{project_name} Workspace",
        "sourceProjectKey": project_key,
    }


def _is_terminal_status(status: str) -> bool:
    normalized = str(status or "").strip().lower()
    return normalized in {
        "done",
        "closed",
        "resolved",
        "fini",
        "résolu",
        "resolu",
        "annulé",
        "annule",
        "terminé",
        "termine",
    }


def _attention_risk_level(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def _issue_assignee_label(issue: dict) -> str:
    assignee = str(issue.get("assignee") or "").strip()
    return assignee if assignee and assignee != "Unassigned" else "the owner"


def _attention_recommended_action(issue: dict, *, blocked: bool, unassigned: bool, validation: bool, score: int) -> str:
    key = str(issue.get("key") or "this ticket")
    if blocked:
        return f"Unblock {key}: contact {_issue_assignee_label(issue)} and clarify the blocking dependency today."
    if unassigned:
        return f"Assign an owner for {key} before the next delivery check-in."
    if validation:
        return f"Confirm the decision needed for {key} so validation does not stall."
    if score >= 60:
        return f"Review {key} during today's delivery check-in and decide the next action."
    return f"Monitor {key} during today's delivery check-in."


def _build_pm_inbox(open_issues: List[dict], blockers: List[dict]) -> List[dict]:
    blocker_keys = {str(issue.get("key") or "") for issue in blockers}
    inbox: List[dict] = []

    for issue in open_issues:
        if _is_terminal_status(str(issue.get("status") or "")):
            continue

        key = str(issue.get("key") or "")
        status = str(issue.get("status") or "")
        priority = str(issue.get("priority") or "")
        assignee = str(issue.get("assignee") or "")
        normalized_status = status.lower()
        normalized_priority = priority.lower()
        blocked = key in blocker_keys or "block" in normalized_status
        unassigned = not assignee or assignee == "Unassigned"
        validation = any(token in normalized_status for token in ("uat", "validation", "test", "review"))

        score = 0
        evidence: List[str] = []

        if blocked:
            score += 45
            evidence.append("Blocked status")
        if normalized_priority in {"highest", "critical", "blocker", "bloqueur"}:
            score += 35
            evidence.append("Highest priority")
        elif normalized_priority in {"high", "critique"}:
            score += 25
            evidence.append("High priority")
        if unassigned:
            score += 20
            evidence.append("No assignee")
        if validation:
            score += 18
            evidence.append(f"Currently in {status}")

        if score <= 0:
            continue

        attention_score = min(100, score)
        inbox.append(
            {
                "ticketKey": key,
                "summary": issue.get("summary") or "Untitled issue",
                "attentionScore": attention_score,
                "riskLevel": _attention_risk_level(attention_score),
                "evidence": evidence,
                "recommendedAction": _attention_recommended_action(
                    issue,
                    blocked=blocked,
                    unassigned=unassigned,
                    validation=validation,
                    score=attention_score,
                ),
                "sourceRefs": [f"jira_issues:{key}"],
            }
        )

    inbox.sort(key=lambda item: item["attentionScore"], reverse=True)
    return inbox[:5]


def _build_workspace_maturity(open_issues: List[dict], blockers: List[dict], *, sprint_health_available: bool) -> dict:
    if not open_issues:
        return {
            "level": "new",
            "confidence": 0.2,
            "reasons": ["No in-scope Jira issues were indexed yet"],
        }

    reasons = [f"{len(open_issues)} Jira issue(s) indexed"]
    if blockers:
        reasons.append(f"{len(blockers)} blocker or highest-priority item(s) detected")
    if sprint_health_available:
        reasons.append("Sprint confidence estimated from current Jira state")

    return {
        "level": "indexed",
        "confidence": 0.45,
        "reasons": reasons,
    }


def _build_ready_reports(pm_inbox: List[dict], sprint_health: dict) -> List[dict]:
    if not pm_inbox:
        return []
    return [
        {
            "title": "Daily delivery brief",
            "detail": (
                f"{len(pm_inbox)} attention item(s) and sprint status "
                f"{sprint_health.get('value', 'Unknown')} are ready to summarize."
            ),
        }
    ]


def _search_issues_with_fallbacks(
    tool_names: List[str],
    invoke: Callable[[str, dict], dict],
    *,
    cloud_id: Optional[str],
    jql_variants: tuple[str, ...],
    max_results: int,
) -> List[dict]:
    """Try several JQL queries until one returns issues."""
    for jql in jql_variants:
        issues = _search_issues(
            tool_names,
            invoke,
            cloud_id=cloud_id,
            jql=jql,
            max_results=max_results,
        )
        if issues:
            return issues
    return []


def _resolve_cloud_id(
    tool_names: List[str],
    invoke: Callable[[str, dict], dict],
) -> Optional[str]:
    resource_tool = _find_tool(
        tool_names,
        "getAccessibleAtlassianResources",
        "getAtlassianResources",
        "listAccessibleAtlassianResources",
    )
    if not resource_tool:
        return None
    payload = _parse_tool_payload(invoke(resource_tool, {}))
    cloud_id = _extract_cloud_id(payload)
    if cloud_id:
        return cloud_id
    for text in _walk_strings(payload):
        if "atlassian.net" in text:
            return text.strip()
    return None


def _append_key_cursor(jql: str, last_key: str) -> str:
    """Append a key cursor for MCP servers that ignore start_at pagination."""
    safe_key = str(last_key).replace('"', '\\"').strip()
    if not safe_key:
        return jql

    cursor_clause = f'key > "{safe_key}"'
    upper = jql.upper()
    order_idx = upper.rfind(" ORDER BY ")
    if order_idx >= 0:
        base = jql[:order_idx].strip()
        order = jql[order_idx:]
        join = " AND " if base else ""
        return f"{base}{join}{cursor_clause}{order}"

    join = " AND " if jql.strip() else ""
    return f"{jql}{join}{cursor_clause} ORDER BY key ASC"


def _search_issues(
    tool_names: List[str],
    invoke: Callable[[str, dict], dict],
    *,
    cloud_id: Optional[str],
    jql: str,
    max_results: int = 10,
) -> List[dict]:
    search_tool = _find_tool(
        tool_names,
        "jira_search",
        "searchJiraIssuesUsingJql",
        "searchJiraIssues",
        "jiraSearch",
    )
    if not search_tool:
        return []

    page_size = max(1, max_results)
    all_issues: List[dict] = []
    seen_keys: set[str] = set()
    start_at = 0
    use_key_cursor = False
    cursor_jql = jql

    while True:
        payload = _search_issues_page(
            tool_name=search_tool,
            tool_names=tool_names,
            invoke=invoke,
            cloud_id=cloud_id,
            jql=cursor_jql,
            page_size=page_size,
            start_at=0 if use_key_cursor else start_at,
        )
        raw_issues = _extract_issues(payload)
        page = [_normalize_issue(issue) for issue in raw_issues]
        added = 0
        for issue in page:
            key = str(issue.get("key") or "").strip()
            dedupe_key = key or f"{start_at}:{added}:{issue.get('summary', '')}"
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            all_issues.append(issue)
            added += 1

        total = _extract_total(payload)
        if not page:
            break

        if (
            not use_key_cursor
            and start_at > 0
            and added == 0
            and len(all_issues) >= page_size
        ):
            # Some MCP servers ignore start_at and keep returning page 1.
            last_key = str(all_issues[-1].get("key") or "").strip()
            if last_key:
                use_key_cursor = True
                cursor_jql = _append_key_cursor(jql, last_key)
                continue
            break

        if len(page) < page_size or (total is not None and len(all_issues) >= total) or added == 0:
            break

        if use_key_cursor:
            last_key = str(all_issues[-1].get("key") or "").strip()
            if not last_key:
                break
            cursor_jql = _append_key_cursor(jql, last_key)
        else:
            start_at += page_size

    return all_issues


def _search_issues_page(
    *,
    tool_name: str,
    tool_names: List[str],
    invoke: Callable[[str, dict], dict],
    cloud_id: Optional[str],
    jql: str,
    page_size: int,
    start_at: int,
) -> Any:
    tool_key = tool_name.lower()
    if tool_key == "jira_search":
        fields_arg: Any = _DASHBOARD_ISSUE_FIELDS_CSV
        base_args: Dict[str, Any] = {"jql": jql, "limit": page_size}
        paginated_variants = [
            {**base_args, "start_at": start_at},
            {**base_args, "startAt": start_at},
        ]
    else:
        fields_arg = _DASHBOARD_ISSUE_FIELDS
        base_args = {"jql": jql, "maxResults": page_size, "startAt": start_at}
        if cloud_id:
            base_args["cloudId"] = cloud_id
        paginated_variants = [base_args]

    # First try explicit pagination with fields, then without fields. On the
    # first page only, keep the legacy no-offset shape as a compatibility
    # fallback for MCP servers that reject pagination parameters.
    arg_variants: List[Dict[str, Any]] = []
    for args in paginated_variants:
        arg_variants.append({**args, "fields": fields_arg})
        arg_variants.append(args)
    if start_at == 0:
        legacy_args = {"jql": jql, "limit": page_size} if tool_key == "jira_search" else {"jql": jql, "maxResults": page_size}
        if tool_key != "jira_search" and cloud_id:
            legacy_args["cloudId"] = cloud_id
        arg_variants.extend([{**legacy_args, "fields": fields_arg}, legacy_args])

    last_error: Optional[JiraDashboardError] = None
    for args in arg_variants:
        try:
            return _parse_tool_payload(invoke(tool_name, args))
        except JiraDashboardError as exc:
            last_error = exc
            logger.debug("Jira search failed with args %s: %s", sorted(args.keys()), exc)

    if last_error:
        raise last_error
    return {}


def _extract_total(payload: Any) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    value = payload.get("total")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    nested = payload.get("issues")
    if isinstance(nested, dict):
        value = nested.get("total")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _find_issue_detail_tool(tool_names: List[str]) -> Optional[str]:
    exact_candidates = {
        "jira_get_issue",
        "get_issue",
        "getissue",
        "jira_get_issue_by_key",
        "getissuebykey",
    }
    by_lower = {name.lower(): name for name in tool_names}
    for candidate in exact_candidates:
        found = by_lower.get(candidate)
        if found:
            return found
    for name in tool_names:
        lowered = name.lower()
        if "issue" not in lowered:
            continue
        if "get" not in lowered:
            continue
        if any(skip in lowered for skip in ("image", "sla", "date", "development", "proforma", "watcher", "transition")):
            continue
        return name
    return None


def _extract_single_issue(payload: Any) -> Optional[dict]:
    if isinstance(payload, dict):
        if payload.get("key") or isinstance(payload.get("fields"), dict):
            return payload
        for key in ("issue", "data", "result"):
            value = payload.get(key)
            if isinstance(value, dict):
                issue = _extract_single_issue(value)
                if issue:
                    return issue
        issues = _extract_issues(payload)
        if issues:
            return issues[0]
    elif isinstance(payload, list):
        issues = _extract_issues(payload)
        if issues:
            return issues[0]
    return None


def _issue_detail_arg_variants(
    tool_name: str,
    issue_key: str,
    *,
    include_comments: bool = False,
    comment_limit: int = 50,
) -> List[dict]:
    fields = _DASHBOARD_ISSUE_FIELDS_CSV
    if tool_name.lower() in {"jira_get_issue", "get_issue"}:
        if include_comments:
            return [
                {
                    "issue_key": issue_key,
                    "fields": fields,
                    "comment_limit": comment_limit,
                    "update_history": False,
                },
                {"issue_key": issue_key, "fields": fields, "comment_limit": comment_limit},
                {"issue_key": issue_key, "fields": fields},
                {"issue_key": issue_key},
            ]
        return [
            {"issue_key": issue_key, "fields": fields, "comment_limit": 0, "update_history": False},
            {"issue_key": issue_key, "fields": fields},
            {"issue_key": issue_key},
        ]
    if include_comments:
        return [
            {"issueKey": issue_key, "fields": _DASHBOARD_ISSUE_FIELDS, "commentLimit": comment_limit},
            {"issue_key": issue_key, "fields": fields, "comment_limit": comment_limit},
            {"issueKey": issue_key, "fields": _DASHBOARD_ISSUE_FIELDS},
            {"issue_key": issue_key, "fields": fields},
            {"key": issue_key, "fields": _DASHBOARD_ISSUE_FIELDS},
            {"issueKey": issue_key},
        ]
    return [
        {"issueKey": issue_key, "fields": _DASHBOARD_ISSUE_FIELDS},
        {"issue_key": issue_key, "fields": fields},
        {"key": issue_key, "fields": _DASHBOARD_ISSUE_FIELDS},
        {"issueKey": issue_key},
    ]


def _fetch_issue_attachments_from_tools(
    tool_names: List[str],
    invoke: Callable[[str, dict], dict],
    issue_key: str,
) -> List[dict]:
    detail_tool = _find_issue_detail_tool(tool_names)
    if not detail_tool:
        return []

    for args in _issue_detail_arg_variants(detail_tool, issue_key):
        try:
            payload = _parse_tool_payload(invoke(detail_tool, args))
            detail = _extract_single_issue(payload)
            if not detail:
                continue
            return _issue_attachments(detail, issue_key=issue_key)
        except JiraDashboardError as exc:
            logger.debug("Jira issue detail failed for %s with args %s: %s", issue_key, sorted(args.keys()), exc)
    return []


def fetch_jira_attachment_preview(
    issue_key: str,
    *,
    attachment_id: str = "",
    name: str = "",
) -> tuple[bytes, str]:
    """Load one Jira attachment through an authenticated MCP attachment tool."""
    safe_key = str(issue_key or "").strip()
    if not safe_key:
        raise JiraDashboardError("Issue key is required.")

    cfg = _get_mcp_servers().get(_active_jira_mcp_name())
    if not cfg:
        raise JiraDashboardError("Jira is not configured.")

    from tools.mcp_tool import invoke_mcp_tool, list_connected_mcp_raw_tool_names

    if not _jira_server_connected():
        raise JiraDashboardError("Jira is not connected.")

    tool_names = list_connected_mcp_raw_tool_names(_active_jira_mcp_name())
    download_tool = _find_tool(tool_names, "jira_download_attachments", "download_attachments")
    if not download_tool:
        raise JiraDashboardError("Connected Jira MCP server does not expose attachment download.")

    payload = _parse_tool_payload(invoke_mcp_tool(_active_jira_mcp_name(), download_tool, {"issue_key": safe_key}))
    match = _find_attachment_blob(payload, attachment_id=attachment_id, name=name)
    if not match:
        image_tool = _find_tool(tool_names, "jira_get_issue_images", "get_issue_images")
        if image_tool:
            image_payload = _parse_tool_payload(invoke_mcp_tool(_active_jira_mcp_name(), image_tool, {"issue_key": safe_key}))
            match = _find_attachment_media_file(image_payload, attachment_id=attachment_id, name=name)
    if not match:
        raise JiraDashboardError(
            "Jira attachment content was not returned by the MCP server. "
            "Images require jira_get_issue_images; videos require a Jira MCP download tool that exposes binary content."
        )
    return match


_MEDIA_TAG_RE = re.compile(r"MEDIA:(?P<path>[^\s]+)")


def _find_attachment_media_file(payload: Any, *, attachment_id: str = "", name: str = "") -> Optional[tuple[bytes, str]]:
    text = _payload_text(payload)
    paths = [match.group("path") for match in _MEDIA_TAG_RE.finditer(text)]
    if not paths:
        return None

    wanted_id = str(attachment_id or "").strip().lower()
    wanted_name = str(name or "").strip().lower()

    def score(path: str) -> int:
        lowered = path.lower()
        points = 0
        if wanted_id and wanted_id in lowered:
            points += 4
        if wanted_name and wanted_name in lowered:
            points += 3
        return points

    selected = max(paths, key=score)
    if (wanted_id or wanted_name) and score(selected) == 0 and len(paths) > 1:
        selected = paths[0]

    target = Path(selected)
    if not target.is_file():
        return None
    media_type = mimetypes.guess_type(str(target))[0] or "image/png"
    return target.read_bytes(), media_type


def _payload_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        return "\n".join(_payload_text(value) for value in payload.values())
    if isinstance(payload, list):
        return "\n".join(_payload_text(item) for item in payload)
    return ""


def _find_attachment_blob(payload: Any, *, attachment_id: str = "", name: str = "") -> Optional[tuple[bytes, str]]:
    wanted_id = str(attachment_id or "").strip().lower()
    wanted_name = str(name or "").strip().lower()
    candidates: List[tuple[str, str, str]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            mime_type = _first_string(node, "mimeType", "mime_type", "contentType", "content_type")
            data = _first_string(node, "blob", "data", "base64", "content")
            uri = _first_string(node, "uri", "url", "name", "filename", "fileName", "title", "id")
            resource = node.get("resource")
            if isinstance(resource, dict):
                mime_type = mime_type or _first_string(resource, "mimeType", "mime_type", "contentType", "content_type")
                data = data or _first_string(resource, "blob", "data", "base64", "content")
                uri = uri or _first_string(resource, "uri", "url", "name", "filename", "fileName", "title", "id")
            if data and (mime_type or uri):
                candidates.append((uri, mime_type or "application/octet-stream", data))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)

    def score(candidate: tuple[str, str, str]) -> int:
        uri = candidate[0].lower()
        points = 0
        if wanted_id and wanted_id in uri:
            points += 4
        if wanted_name and wanted_name in uri:
            points += 3
        return points

    if not candidates:
        return None

    selected = max(candidates, key=score)
    if (wanted_id or wanted_name) and score(selected) == 0 and len(candidates) > 1:
        return None

    try:
        return base64.b64decode(selected[2]), selected[1]
    except Exception as exc:
        raise JiraDashboardError("Jira attachment content was not valid base64.") from exc


def fetch_jira_issue_attachments(issue_key: str) -> List[dict]:
    """Load Jira attachments for one issue on demand."""
    safe_key = str(issue_key or "").strip()
    if not safe_key:
        raise JiraDashboardError("Issue key is required.")

    cfg = _get_mcp_servers().get(_active_jira_mcp_name())
    if not cfg:
        raise JiraDashboardError("Jira is not configured.")

    from tools.mcp_tool import invoke_mcp_tool, list_connected_mcp_raw_tool_names

    if not _jira_server_connected():
        raise JiraDashboardError("Jira is not connected.")

    tool_names = list_connected_mcp_raw_tool_names(_active_jira_mcp_name())
    if not tool_names:
        raise JiraDashboardError("Connected to Jira MCP, but no tools were exposed.")

    def invoke(tool_name: str, arguments: dict) -> dict:
        return invoke_mcp_tool(_active_jira_mcp_name(), tool_name, arguments)

    return _fetch_issue_attachments_from_tools(tool_names, invoke, safe_key)


def _humanize_dashboard_error(message: str) -> str:
    if "unreachable after" in message.lower() and "consecutive failures" in message.lower():
        return (
            "Jira MCP paused after repeated failures. Click Refresh to reconnect, "
            "or update your credentials if the problem continues."
        )
    return message


def fetch_jira_dashboard(
    *,
    force_sample: bool = False,
    reconnect: bool = False,
    project_key: Optional[str] = None,
) -> dict:
    """Return dashboard data from Jira MCP, or sample data when disconnected."""
    if force_sample:
        return _sample_dashboard()

    cfg = _get_mcp_servers().get(_active_jira_mcp_name())
    if not cfg:
        return _sample_dashboard()

    if reconnect:
        from tools.mcp_tool import reconnect_mcp_server

        reconnect_mcp_server(_active_jira_mcp_name(), cfg)

    from tools.mcp_tool import invoke_mcp_tool, list_connected_mcp_raw_tool_names

    # Read-only: never spawn MCP / OAuth on dashboard load. Connection happens only
    # when the user explicitly clicks Connect or saves credentials.
    if not _jira_server_connected():
        sample = _sample_dashboard()
        if _uses_env_auth(cfg):
            sample["connection"]["message"] = (
                "Jira credentials are saved. Click “Jira credentials” to update them, "
                "then save to test the connection."
            )
        else:
            sample["connection"]["message"] = (
                "Jira is not connected yet. Use “Jira credentials (recommended)” or "
                "“Connect Jira” when you are ready — nothing starts until you click."
            )
        return sample

    tool_names = list_connected_mcp_raw_tool_names(_active_jira_mcp_name())
    if not tool_names:
        sample = _sample_dashboard()
        sample["connection"]["status"] = "error"
        sample["connection"]["message"] = "Connected to Jira MCP, but no tools were exposed."
        return sample

    def invoke(tool_name: str, arguments: dict) -> dict:
        return invoke_mcp_tool(_active_jira_mcp_name(), tool_name, arguments)

    try:
        projects = _fetch_projects(tool_names, invoke)
        selected_project = _resolve_project_key(projects, project_key)
        issue_jqls = _issue_jql_variants(selected_project)
        blocker_jqls = _blocker_jql_variants(selected_project)

        cloud_id = _ensure_cloud_id(cfg, tool_names, invoke)
        open_issues = _search_issues_with_fallbacks(
            tool_names,
            invoke,
            cloud_id=cloud_id,
            jql_variants=issue_jqls,
            max_results=_DASHBOARD_ISSUE_PAGE_SIZE,
        )
        blockers = _search_issues_with_fallbacks(
            tool_names,
            invoke,
            cloud_id=cloud_id,
            jql_variants=blocker_jqls,
            max_results=_DASHBOARD_ISSUE_PAGE_SIZE,
        )
    except JiraDashboardError as exc:
        sample = _sample_dashboard()
        sample["connection"]["status"] = "error"
        sample["connection"]["message"] = _humanize_dashboard_error(str(exc))
        return sample
    except Exception as exc:
        logger.exception("Jira dashboard fetch failed")
        sample = _sample_dashboard()
        sample["connection"]["status"] = "error"
        sample["connection"]["message"] = _humanize_dashboard_error(str(exc))
        return sample

    open_count = len(open_issues)
    blocker_count = len(blockers)
    unassigned = sum(1 for issue in open_issues if issue["assignee"] == "Unassigned")

    sprint_tone = "good"
    sprint_value = "Healthy"
    sprint_detail = "Open priorities have owners and no urgent blockers surfaced."
    if blocker_count:
        sprint_tone = "warning"
        sprint_value = "Watch"
        sprint_detail = f"{blocker_count} blocked or highest-priority item(s) need attention."
    elif unassigned >= max(2, open_count // 2):
        sprint_tone = "warning"
        sprint_value = "Watch"
        sprint_detail = f"{unassigned} open priority(ies) still lack an owner."

    sprint_health_metric = _metric(
        "Sprint health",
        sprint_value,
        sprint_detail,
        sprint_tone,
    )

    confidence = max(35, min(95, 90 - blocker_count * 12 - unassigned * 4))

    priorities = open_issues
    selected_name = next(
        (p.get("name") for p in projects if p.get("key") == selected_project),
        selected_project or "",
    )
    project_scope = f"{selected_name} ({selected_project})" if selected_project else "your workspace"
    risks: List[dict] = []
    if blocker_count:
        risks.append(
            {
                "label": "Blocked work",
                "detail": f"{blocker_count} Jira item(s) are blocked or marked highest priority.",
            }
        )
    if unassigned:
        risks.append(
            {
                "label": "Missing owners",
                "detail": f"{unassigned} open priority(ies) do not have an assignee yet.",
            }
        )
    if not risks:
        risks.append(
            {
                "label": "Stakeholder visibility",
                "detail": "Use VisualQ for quality signals and Messaging for stakeholder channels.",
            }
        )

    pm_inbox = _build_pm_inbox(open_issues, blockers)
    workspace = _workspace_from_project(selected_project, projects)
    workspace_maturity = _build_workspace_maturity(
        open_issues,
        blockers,
        sprint_health_available=True,
    )
    reports_ready = _build_ready_reports(pm_inbox, sprint_health_metric)
    actions = [item["recommendedAction"] for item in pm_inbox[:3]]
    actions.extend(
        [
            "Review open priorities and identify blockers",
            "Confirm owners for unassigned Jira tickets",
            "Prepare a stakeholder-ready delivery brief",
        ]
    )

    return {
        "connection": {
            "status": "connected",
            "message": (
                f"Live Jira data for {project_scope}."
                if selected_project
                else "Live Jira data loaded through Jira MCP."
            ),
            "authenticated": True,
            "toolCount": len(tool_names),
        },
        "sampleData": False,
        "projects": projects,
        "selectedProjectKey": selected_project,
        "workspace": workspace,
        "metrics": [
            _metric(
                "Delivery confidence",
                f"{confidence}%",
                f"{open_count} open item(s) in {project_scope}.",
                "good" if confidence >= 70 else "warning",
            ),
            sprint_health_metric,
            _metric(
                "Jira status",
                "Connected",
                f"{len(tool_names)} MCP tools available for Jira workflows.",
                "good",
            ),
        ],
        "priorities": priorities,
        "blockers": blockers,
        "risks": risks,
        "actions": actions,
        "sprintHealth": sprint_health_metric,
        "pmInbox": pm_inbox,
        "workspaceMaturity": workspace_maturity,
        "reportsReady": reports_ready,
    }
