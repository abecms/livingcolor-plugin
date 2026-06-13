"""GitHub.com VCS provider helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

_GITHUB_API_URL = "https://api.github.com"
_FETCH_TIMEOUT_SECONDS = 30


@dataclass
class GitHubDiscoveryResult:
    repos: list[dict[str, Any]] = field(default_factory=list)
    default_repo: str | None = None
    warnings: list[str] = field(default_factory=list)


def _read_mcp_env(mcp_config: dict) -> dict[str, str]:
    env = mcp_config.get("env") or {}
    if not isinstance(env, dict):
        return {}
    return {str(k): str(v).strip() for k, v in env.items() if v is not None and str(v).strip()}


def github_token_from_config(mcp_config: dict) -> str | None:
    return _read_mcp_env(mcp_config).get("GITHUB_TOKEN")


def build_github_clone_url(repo_id: str, token: str) -> str:
    repo_path = repo_id.strip().removeprefix("github.com/").strip("/")
    return f"https://x-access-token:{quote(token, safe='')}@github.com/{repo_path}.git"


def _project_matches_key(repo: dict[str, Any], project_key: str) -> bool:
    key = project_key.casefold()
    full_name = str(repo.get("full_name") or "").casefold()
    name = str(repo.get("name") or "").casefold()
    return key in full_name or key in name


def _to_repo_entry(repo: dict[str, Any]) -> dict[str, Any]:
    full_name = str(repo.get("full_name") or "").strip("/")
    return {"path": f"github.com/{full_name}" if full_name else "", "githubId": repo.get("id")}


def discover_github_repos(project_key: str, repos: list[dict]) -> GitHubDiscoveryResult:
    normalized_key = (project_key or "").strip()
    if not repos:
        return GitHubDiscoveryResult()
    if len(repos) == 1:
        entry = _to_repo_entry(repos[0])
        return GitHubDiscoveryResult(repos=[entry], default_repo=entry["path"] or None)
    matches = [repo for repo in repos if _project_matches_key(repo, normalized_key)]
    if matches:
        best = max(matches, key=lambda repo: str(repo.get("updated_at") or ""))
        return GitHubDiscoveryResult(
            repos=[_to_repo_entry(repo) for repo in matches],
            default_repo=_to_repo_entry(best)["path"] or None,
        )
    sorted_repos = sorted(repos, key=lambda repo: str(repo.get("full_name") or "").casefold())
    default = _to_repo_entry(sorted_repos[0])["path"] or None
    return GitHubDiscoveryResult(
        repos=[_to_repo_entry(repo) for repo in sorted_repos],
        default_repo=default,
        warnings=[f"No GitHub repository matched project key {normalized_key!r}; defaulting to the first repository alphabetically."],
    )


def _fetch_github_repositories(mcp_config: dict) -> list[dict]:
    token = _read_mcp_env(mcp_config).get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GitHub token is required in MCP config env (GITHUB_TOKEN)")
    repos: list[dict] = []
    page = 1
    while page <= 50:
        url = f"{_GITHUB_API_URL}/user/repos?affiliation=owner,collaborator,organization_member&per_page=100&page={page}"
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API request failed ({exc.code}): {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GitHub API request failed: {exc.reason}") from exc
        if not isinstance(payload, list):
            raise RuntimeError("GitHub API returned an unexpected repositories payload")
        if not payload:
            break
        repos.extend(dict(item) for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            break
        page += 1
    return repos


def discover_github_repos_for_project(project_key: str, mcp_config: dict) -> GitHubDiscoveryResult:
    return discover_github_repos(project_key, _fetch_github_repositories(mcp_config))
