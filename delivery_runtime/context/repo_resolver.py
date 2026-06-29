"""Resolve target repository from readiness hints and project mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from delivery_runtime.context.repo_checkout import ensure_managed_checkout
from delivery_runtime.readiness.project_mapping import load_project_mapping, resolve_recommended_repos


@dataclass(frozen=True)
class ResolvedRepository:
    repo_id: str
    checkout_path: str | None
    conventions: list[str]
    source: str


def _is_plausible_repo_id(value: str) -> bool:
    """Return True when *value* looks like a VCS repo path, not analyst prose."""
    candidate = str(value or "").strip().strip("/")
    if not candidate:
        return False
    if any(char in candidate for char in " ()"):
        return False
    if candidate.count("/") < 1:
        return False
    return True


def _filter_repo_candidates(candidates: list[str]) -> list[str]:
    return [item for item in candidates if _is_plausible_repo_id(item)]


def resolve_repository(
    *,
    project_key: str,
    snapshot: dict[str, Any],
    recommended_repos: list[str],
    override_repo: str | None = None,
) -> ResolvedRepository | None:
    mapping = load_project_mapping()
    project_cfg = mapping.get(project_key) or mapping.get(project_key.upper()) or {}
    if not isinstance(project_cfg, dict):
        project_cfg = {}

    repo_id = (override_repo or "").strip()
    source = "override"

    if not repo_id and recommended_repos:
        filtered = _filter_repo_candidates([str(item).strip() for item in recommended_repos if str(item).strip()])
        if filtered:
            repo_id = filtered[0]
            source = "readiness"

    if not repo_id:
        inferred = resolve_recommended_repos(project_key, snapshot)
        if inferred:
            repo_id = inferred[0]
            source = "mapping"

    if not repo_id:
        return None

    if not _is_plausible_repo_id(repo_id):
        return None

    checkout_path = _lookup_checkout_path(project_cfg, repo_id)
    if not checkout_path:
        checkout_path = ensure_managed_checkout(
            project_key=project_key,
            repo_id=repo_id,
            project_cfg=project_cfg,
        )
    conventions = _lookup_conventions(project_cfg, repo_id)
    return ResolvedRepository(
        repo_id=repo_id,
        checkout_path=checkout_path,
        conventions=conventions,
        source=source,
    )


def _iter_repo_entries(project_cfg: dict[str, Any]):
    repos = project_cfg.get("repos") or []
    if isinstance(repos, list):
        for entry in repos:
            if isinstance(entry, dict):
                yield entry
        return
    if isinstance(repos, dict):
        for repo_key, entry in repos.items():
            if isinstance(entry, dict):
                yield {**entry, "path": str(entry.get("path") or repo_key).strip()}


def _repo_entry_matches(entry: dict[str, Any], repo_id: str) -> bool:
    path = str(entry.get("path") or "").strip()
    if not path:
        return False
    normalized = repo_id.strip().strip("/")
    return path == normalized or path.endswith(f"/{normalized.split('/')[-1]}")


def _lookup_checkout_path(project_cfg: dict[str, Any], repo_id: str) -> str | None:
    for entry in _iter_repo_entries(project_cfg):
        if _repo_entry_matches(entry, repo_id):
            path = str(entry.get("checkout_path") or "").strip()
            if path:
                return path
    default_path = str(project_cfg.get("checkout_path") or "").strip()
    return default_path or None


def _lookup_conventions(project_cfg: dict[str, Any], repo_id: str) -> list[str]:
    conventions: list[str] = []
    for entry in _iter_repo_entries(project_cfg):
        if _repo_entry_matches(entry, repo_id):
            conventions.extend(_as_str_list(entry.get("conventions")))
    conventions.extend(_as_str_list(project_cfg.get("conventions")))
    return _dedupe(conventions)


def _as_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
