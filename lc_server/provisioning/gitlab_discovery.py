"""GitLab repository discovery for project automation provisioning."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

_DEFAULT_GITLAB_API_URL = "https://gitlab.com/api/v4"
_FETCH_TIMEOUT_SECONDS = 30


@dataclass
class GitLabDiscoveryResult:
    repos: list[dict[str, Any]] = field(default_factory=list)
    default_repo: str | None = None
    warnings: list[str] = field(default_factory=list)


def _project_matches_key(project: dict[str, Any], project_key: str) -> bool:
    key = project_key.casefold()
    path = str(project.get("path_with_namespace") or "").casefold()
    name = str(project.get("name") or "").casefold()
    return key in path or key in name


def _to_repo_entry(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(project.get("path_with_namespace") or ""),
        "gitlabId": project.get("id"),
    }


def discover_gitlab_repos(project_key: str, projects: list[dict]) -> GitLabDiscoveryResult:
    """Apply heuristics to pick a default repo from a GitLab project list."""
    normalized_key = (project_key or "").strip()
    if not projects:
        return GitLabDiscoveryResult()

    if len(projects) == 1:
        repo_path = str(projects[0].get("path_with_namespace") or "")
        return GitLabDiscoveryResult(
            repos=[_to_repo_entry(projects[0])],
            default_repo=repo_path or None,
        )

    matches = [project for project in projects if _project_matches_key(project, normalized_key)]

    if matches:
        if len(matches) == 1:
            repo_path = str(matches[0].get("path_with_namespace") or "")
            return GitLabDiscoveryResult(
                repos=[_to_repo_entry(matches[0])],
                default_repo=repo_path or None,
            )

        best = max(
            matches,
            key=lambda project: str(project.get("last_activity_at") or ""),
        )
        repo_path = str(best.get("path_with_namespace") or "")
        return GitLabDiscoveryResult(
            repos=[_to_repo_entry(match) for match in matches],
            default_repo=repo_path or None,
        )

    sorted_projects = sorted(
        projects,
        key=lambda project: str(project.get("path_with_namespace") or "").casefold(),
    )
    default_path = str(sorted_projects[0].get("path_with_namespace") or "") or None
    warning = (
        f"No GitLab repository matched project key {normalized_key!r}; "
        "defaulting to the first repository alphabetically."
    )
    return GitLabDiscoveryResult(
        repos=[_to_repo_entry(project) for project in sorted_projects],
        default_repo=default_path,
        warnings=[warning],
    )


def _read_mcp_env(mcp_config: dict) -> dict[str, str]:
    env = mcp_config.get("env") or {}
    if not isinstance(env, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in env.items():
        if value is None:
            continue
        text = str(value).strip()
        if text:
            out[str(key)] = text
    return out


def _normalize_api_base_url(api_url: str) -> str:
    normalized = api_url.strip().rstrip("/")
    if normalized.endswith("/api/v4"):
        return normalized
    return f"{normalized}/api/v4"


def _fetch_gitlab_projects(mcp_config: dict) -> list[dict]:
    env = _read_mcp_env(mcp_config)
    token = env.get("GITLAB_PERSONAL_ACCESS_TOKEN") or env.get("GITLAB_TOKEN")
    if not token:
        raise ValueError(
            "GitLab token is required in MCP config env (GITLAB_PERSONAL_ACCESS_TOKEN or GITLAB_TOKEN)"
        )

    api_base = _normalize_api_base_url(env.get("GITLAB_API_URL") or _DEFAULT_GITLAB_API_URL)
    projects: list[dict] = []
    page = 1

    while page <= 50:
        url = f"{api_base}/projects?membership=true&simple=true&per_page=100&page={page}"
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
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitLab API request failed ({exc.code}): {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GitLab API request failed: {exc.reason}") from exc

        if not isinstance(payload, list):
            raise RuntimeError("GitLab API returned an unexpected projects payload")

        if not payload:
            break

        for item in payload:
            if isinstance(item, dict):
                projects.append(dict(item))

        if len(payload) < 100:
            break
        page += 1

    return projects


def discover_gitlab_repos_for_project(project_key: str, mcp_config: dict) -> GitLabDiscoveryResult:
    projects = _fetch_gitlab_projects(mcp_config)
    return discover_gitlab_repos(project_key, projects)
