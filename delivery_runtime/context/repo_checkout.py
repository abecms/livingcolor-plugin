"""Managed Git checkouts under ~/.livingcolor/{PROJECT_KEY}/."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

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

    clone_url = _build_clone_url(repo_id, project_cfg, project_key=project_key)
    if not clone_url:
        from lc_server.integrations.vcs.provider import normalize_vcs_provider

        provider = normalize_vcs_provider(project_cfg.get("vcs"))
        logger.warning(
            "Cannot clone %s for project %s into %s: %s credentials missing "
            "(project_mapping.yaml integrations or global Hermes MCP %s config)",
            repo_id,
            project_key,
            target,
            provider.title(),
            provider,
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


def has_gitlab_clone_credentials(
    project_cfg: dict[str, Any],
    *,
    project_key: str | None = None,
) -> bool:
    """Return True when GitLab token env is available for managed clone."""
    from lc_server.integrations.vcs.gitlab import gitlab_token_from_config

    key = (project_key or "").strip().upper()
    config = _project_or_global_mcp_config(project_cfg, "gitlab", key)
    return bool(gitlab_token_from_config(config))


def has_clone_credentials(
    project_cfg: dict[str, Any],
    *,
    project_key: str | None = None,
) -> bool:
    """Return True when VCS credentials are available for the active provider."""
    from lc_server.integrations.vcs.provider import normalize_vcs_provider

    key = (project_key or "").strip().upper()
    provider = normalize_vcs_provider(project_cfg.get("vcs"))
    if provider == "github":
        from lc_server.integrations.vcs.github import github_token_from_config

        config = _project_or_global_mcp_config(project_cfg, "github", key)
        return bool(github_token_from_config(config))

    from lc_server.integrations.vcs.gitlab import gitlab_token_from_config

    config = _project_or_global_mcp_config(project_cfg, "gitlab", key)
    return bool(gitlab_token_from_config(config))


def _project_or_global_mcp_config(project_cfg: dict[str, Any], server_name: str, project_key: str) -> dict[str, Any]:
    integrations = project_cfg.get("integrations") if isinstance(project_cfg, dict) else {}
    integrations_map = integrations if isinstance(integrations, dict) else {}
    servers = integrations_map.get("mcp_servers")
    servers_map = servers if isinstance(servers, dict) else {}
    direct = servers_map.get(server_name)
    if isinstance(direct, dict) and direct:
        return dict(direct)
    if project_key:
        from delivery_runtime.readiness.project_settings import resolve_project_mcp_server

        return resolve_project_mcp_server(project_key, server_name)
    return {}


def _build_clone_url(
    repo_id: str,
    project_cfg: dict[str, Any],
    *,
    project_key: str | None = None,
) -> str | None:
    from lc_server.integrations.vcs.provider import normalize_vcs_provider

    provider = normalize_vcs_provider(project_cfg.get("vcs"))
    key = (project_key or "").strip().upper()
    if provider == "github":
        from lc_server.integrations.vcs.github import build_github_clone_url, github_token_from_config

        config = _project_or_global_mcp_config(project_cfg, "github", key)
        token = github_token_from_config(config)
        return build_github_clone_url(repo_id, token) if token else None

    from lc_server.integrations.vcs.gitlab import build_gitlab_clone_url

    config = _project_or_global_mcp_config(project_cfg, "gitlab", key)
    return build_gitlab_clone_url(repo_id, config)
