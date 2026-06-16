from __future__ import annotations

from pathlib import Path

from lc_constants import get_livingcolor_home

VALID_ROLES = frozenset({"orchestrator", "analyst", "planner", "developer", "publisher", "reporter"})


def _normalize_project_key(project_key: str) -> str:
    key = (project_key or "").strip().upper()
    if not key:
        raise ValueError("project_key is required")
    return key


def _normalize_role(role: str) -> str:
    normalized = (role or "").strip().lower()
    if normalized not in VALID_ROLES:
        raise ValueError(f"Invalid agent role: {role!r}")
    return normalized


def get_project_root(project_key: str) -> Path:
    return get_livingcolor_home() / "projects" / _normalize_project_key(project_key)


def get_agents_dir(project_key: str) -> Path:
    return get_project_root(project_key) / "agents"


def get_agent_manifest_path(project_key: str, role: str) -> Path:
    return get_agents_dir(project_key) / f"{_normalize_role(role)}.yaml"


def get_automation_state_path(project_key: str) -> Path:
    return get_project_root(project_key) / "automation.yaml"


def list_provisioned_project_keys() -> list[str]:
    root = get_livingcolor_home() / "projects"
    if not root.is_dir():
        return []
    keys: list[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "automation.yaml").is_file():
            keys.append(child.name.upper())
    return keys
