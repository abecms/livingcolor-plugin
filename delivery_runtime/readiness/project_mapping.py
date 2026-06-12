"""Static Jira project → repository mapping for readiness scoring."""

from __future__ import annotations

from typing import Any

import yaml

from delivery_runtime.persistence.paths import get_project_mapping_path


def mapping_file_path():
    return get_project_mapping_path()


def load_project_mapping() -> dict[str, Any]:
    path = mapping_file_path()
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def resolve_recommended_repos(project_key: str, snapshot: dict[str, Any]) -> list[str]:
    mapping = load_project_mapping()
    project_cfg = mapping.get(project_key) or mapping.get(project_key.upper()) or {}
    if not isinstance(project_cfg, dict):
        return []

    labels = snapshot.get("labels") or []
    label_set = {str(label).lower() for label in labels if label}

    repos: list[str] = []
    for rule in project_cfg.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        label = str(rule.get("label") or "").lower()
        repo = str(rule.get("repo") or "").strip()
        if label and label in label_set and repo:
            repos.append(repo)

    default_repo = str(project_cfg.get("default_repo") or "").strip()
    if not repos and default_repo:
        repos.append(default_repo)

    return repos


def resolve_configured_integration_branch(project_key: str) -> str | None:
    """Return the per-project MR target branch from project_mapping.yaml, if set."""
    project_cfg = load_project_mapping_entry(project_key)
    if not project_cfg:
        return None
    branch = str(project_cfg.get("integration_branch") or "").strip()
    return branch or None


def load_project_mapping_entry(project_key: str) -> dict[str, Any]:
    """Return the mapping block for one LivingColor project key."""
    mapping = load_project_mapping()
    key = str(project_key or "").strip().upper()
    if not key:
        return {}
    project_cfg = mapping.get(key) or mapping.get(project_key) or {}
    return project_cfg if isinstance(project_cfg, dict) else {}
