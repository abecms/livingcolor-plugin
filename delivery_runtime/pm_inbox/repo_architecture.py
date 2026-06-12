"""Persist repository architecture profiles after the first repo scan."""

from __future__ import annotations

from typing import Any

from delivery_runtime.context.repo_architecture import (
    analyze_repository_architecture,
    architecture_profile_is_current,
)
from delivery_runtime.context.repo_resolver import resolve_repository
from delivery_runtime.pm_inbox.project_memory import load_existing_memory
from delivery_runtime.readiness.project_mapping import load_project_mapping


def ensure_project_repo_architecture(*, project_key: str) -> dict[str, Any] | None:
    """Analyze mapped repository checkout once and store the profile in project memory."""
    project_key = project_key.strip().upper()
    mapping = load_project_mapping()
    project_cfg = mapping.get(project_key) or mapping.get(project_key.upper()) or {}
    if not isinstance(project_cfg, dict):
        return None

    default_repo = str(project_cfg.get("default_repo") or "").strip()
    if not default_repo:
        return None

    resolved = resolve_repository(
        project_key=project_key,
        snapshot={"projectKey": project_key},
        recommended_repos=[default_repo],
    )
    if not resolved or not resolved.checkout_path:
        return None

    existing_memory = load_existing_memory(project_key=project_key)
    existing_profile = existing_memory.get("repositoryArchitecture")
    if architecture_profile_is_current(
        existing_profile,
        repo_id=resolved.repo_id,
        checkout_path=resolved.checkout_path,
    ):
        return existing_profile if isinstance(existing_profile, dict) else None

    profile = analyze_repository_architecture(
        resolved.checkout_path,
        repo_id=resolved.repo_id,
    )
    return profile


def merge_repo_architecture(memory: dict[str, Any], *, project_key: str) -> dict[str, Any]:
    """Attach repository architecture to project memory when available."""
    profile = ensure_project_repo_architecture(project_key=project_key)
    if not profile:
        return memory
    merged = dict(memory)
    merged["repositoryArchitecture"] = profile
    return merged
