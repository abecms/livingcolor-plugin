"""Managed Git checkouts under ~/.livingcolor/{PROJECT_KEY}/."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from delivery_runtime.shadow.context import allow_internal_git
from lc_constants import get_livingcolor_home

logger = logging.getLogger(__name__)

# Top-level dirs under ~/.livingcolor that are not project repo checkouts.
_MANAGED_CHECKOUT_EXCLUDED_ROOTS = frozenset(
    {
        "cache",
        "config",
        "delivery",
        "evaluation",
        "logs",
        "projects",
        "work_orders",
    }
)


def managed_checkout_path(project_key: str, repo_id: str) -> Path:
    """Return ~/.livingcolor/{PROJECT_KEY}/<namespace>/<repo>."""
    key = (project_key or "").strip().upper()
    if not key:
        raise ValueError("project_key is required")
    parts = [segment for segment in str(repo_id or "").strip().strip("/").split("/") if segment]
    if not parts:
        raise ValueError("repo_id is required")
    return get_livingcolor_home() / key / Path(*parts)


def is_managed_repo_checkout(path: str | Path) -> bool:
    """True when ``path`` is a git checkout under ~/.livingcolor/{PROJECT}/…."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir() or not (resolved / ".git").exists():
        return False
    try:
        relative = resolved.relative_to(get_livingcolor_home().resolve())
    except ValueError:
        return False
    if not relative.parts or relative.parts[0] in _MANAGED_CHECKOUT_EXCLUDED_ROOTS:
        return False
    return True


def managed_project_environment_root(path: str | Path) -> Path | None:
    """Return ~/.livingcolor/{PROJECT_KEY} for a managed checkout path."""
    resolved = Path(path).expanduser().resolve()
    if not is_managed_repo_checkout(resolved):
        return None
    try:
        relative = resolved.relative_to(get_livingcolor_home().resolve())
    except ValueError:
        return None
    return get_livingcolor_home().resolve() / relative.parts[0]


def fetch_managed_checkout(path: str | Path) -> bool:
    """Fetch latest refs from origin without resetting the working tree."""
    resolved = Path(path).expanduser().resolve()
    if not is_managed_repo_checkout(resolved):
        return False
    with allow_internal_git():
        result = subprocess.run(
            ["git", "fetch", "--depth", "1", "origin"],
            cwd=resolved,
            check=False,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        logger.warning(
            "git fetch failed for %s: %s",
            resolved,
            (result.stderr or result.stdout or "").strip(),
        )
        return _is_git_checkout(resolved)
    return True


def ensure_managed_checkout(
    *,
    project_key: str,
    repo_id: str,
    project_cfg: dict[str, Any],
) -> str | None:
    """Clone or refresh a repository into the managed LivingColor project directory."""
    repo_id = str(repo_id or "").strip().strip("/")
    if not repo_id:
        return None

    target = managed_checkout_path(project_key, repo_id)
    if _is_git_checkout(target):
        if _refresh_checkout(target):
            return str(target)
        return None

    clone_url = _build_clone_url(repo_id, project_cfg)
    if not clone_url:
        logger.warning(
            "Cannot clone %s for project %s: GitLab credentials missing in project_mapping.yaml",
            repo_id,
            project_key,
        )
        return None

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not _is_git_checkout(target):
        return None

    if not _clone_repository(clone_url, target):
        return None
    return str(target) if _is_git_checkout(target) else None


def _is_git_checkout(path: Path) -> bool:
    return path.is_dir() and (path / ".git").exists()


def _clone_repository(clone_url: str, target: Path) -> bool:
    with allow_internal_git():
        result = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        logger.warning(
            "git clone failed for %s: %s",
            target,
            (result.stderr or result.stdout or "").strip(),
        )
        return False
    return True


def _refresh_checkout(path: Path) -> bool:
    with allow_internal_git():
        fetch = subprocess.run(
            ["git", "fetch", "--depth", "1", "origin"],
            cwd=path,
            check=False,
            capture_output=True,
            text=True,
        )
        if fetch.returncode != 0:
            logger.warning(
                "git fetch failed for %s: %s",
                path,
                (fetch.stderr or fetch.stdout or "").strip(),
            )
            return _is_git_checkout(path)

        reset = subprocess.run(
            ["git", "reset", "--hard", "@{u}"],
            cwd=path,
            check=False,
            capture_output=True,
            text=True,
        )
        if reset.returncode != 0:
            # Detached or missing upstream — keep the existing checkout usable.
            logger.debug(
                "git reset skipped for %s: %s",
                path,
                (reset.stderr or reset.stdout or "").strip(),
            )
    return _is_git_checkout(path)


def _build_clone_url(repo_id: str, project_cfg: dict[str, Any]) -> str | None:
    env = _gitlab_env(project_cfg)
    token = env.get("GITLAB_PERSONAL_ACCESS_TOKEN") or env.get("GITLAB_TOKEN")
    if not token:
        return None

    api_url = env.get("GITLAB_API_URL") or "https://gitlab.com/api/v4"
    parsed = urlparse(api_url.strip())
    host = parsed.netloc or "gitlab.com"
    scheme = parsed.scheme or "https"
    safe_token = quote(token, safe="")
    repo_path = repo_id.strip("/")
    return f"{scheme}://oauth2:{safe_token}@{host}/{repo_path}.git"


def _gitlab_env(project_cfg: dict[str, Any]) -> dict[str, str]:
    integrations = project_cfg.get("integrations") or {}
    if not isinstance(integrations, dict):
        return {}
    mcp_servers = integrations.get("mcp_servers") or {}
    if not isinstance(mcp_servers, dict):
        return {}
    gitlab = mcp_servers.get("gitlab") or {}
    if not isinstance(gitlab, dict):
        return {}
    env = gitlab.get("env") or {}
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
