"""Verify published merge requests against the GitLab REST API."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from lc_server.provisioning.gitlab_discovery import (
    _DEFAULT_GITLAB_API_URL,
    _normalize_api_base_url,
    _read_mcp_env,
)

_FETCH_TIMEOUT_SECONDS = 30


def load_project_gitlab_mcp_config(project_key: str) -> dict[str, Any] | None:
    """Return the project's GitLab MCP server config, falling back to global config."""
    from delivery_runtime.readiness.project_settings import (
        load_project_mcp_servers,
        resolve_project_mcp_server,
    )

    for server_name in ("gitlab", "gitlab-tv5"):
        config = resolve_project_mcp_server(project_key, server_name)
        if config:
            return config

    stored = load_project_mcp_servers(project_key)
    for server_name, config in stored.items():
        if "gitlab" in str(server_name).lower() and isinstance(config, dict) and config:
            return dict(config)

    try:
        from hermes_cli.mcp_config import _get_mcp_servers

        for server_name, config in _get_mcp_servers().items():
            if "gitlab" in str(server_name).lower() and isinstance(config, dict) and config:
                return dict(config)
    except ImportError:
        pass

    return None


def repo_path_from_mr_url(mr_url: str) -> str:
    """Extract 'namespace/project' from a GitLab MR web URL."""
    parsed = urllib.parse.urlparse(mr_url)
    path = parsed.path
    marker = "/-/merge_requests/"
    if marker not in path:
        raise ValueError(f"not a GitLab MR url: {mr_url}")
    return path.split(marker)[0].strip("/")


def verify_merge_request_exists(
    *,
    mcp_config: dict[str, Any],
    repo_path_with_namespace: str,
    mr_iid: int,
) -> dict[str, Any] | None:
    """Fetch the MR from GitLab REST. Returns None when it does not exist (404)."""
    env = _read_mcp_env(mcp_config)
    token = env.get("GITLAB_PERSONAL_ACCESS_TOKEN") or env.get("GITLAB_TOKEN")
    if not token:
        raise ValueError(
            "GitLab token is required in MCP config env (GITLAB_PERSONAL_ACCESS_TOKEN or GITLAB_TOKEN)"
        )

    api_base = _normalize_api_base_url(env.get("GITLAB_API_URL") or _DEFAULT_GITLAB_API_URL)
    encoded_path = urllib.parse.quote(repo_path_with_namespace, safe="")
    url = f"{api_base}/projects/{encoded_path}/merge_requests/{int(mr_iid)}"
    request = urllib.request.Request(
        url,
        headers={
            "PRIVATE-TOKEN": token,
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitLab MR verification failed ({exc.code}): {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitLab MR verification failed: {exc.reason}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("GitLab API returned an unexpected merge request payload")
    return payload
