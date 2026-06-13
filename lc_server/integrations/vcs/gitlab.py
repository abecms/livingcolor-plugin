"""GitLab VCS provider compatibility helpers."""

from __future__ import annotations

from urllib.parse import quote, urlparse


def gitlab_token_from_config(mcp_config: dict) -> str | None:
    env = mcp_config.get("env") or {}
    if not isinstance(env, dict):
        return None
    token = env.get("GITLAB_PERSONAL_ACCESS_TOKEN") or env.get("GITLAB_TOKEN")
    return str(token).strip() if token else None


def build_gitlab_clone_url(repo_id: str, mcp_config: dict) -> str | None:
    token = gitlab_token_from_config(mcp_config)
    if not token:
        return None
    env = mcp_config.get("env") if isinstance(mcp_config.get("env"), dict) else {}
    api_url = str(env.get("GITLAB_API_URL") or "https://gitlab.com/api/v4")
    parsed = urlparse(api_url.strip())
    host = parsed.netloc or "gitlab.com"
    scheme = parsed.scheme or "https"
    return f"{scheme}://oauth2:{quote(token, safe='')}@{host}/{repo_id.strip('/')}.git"
