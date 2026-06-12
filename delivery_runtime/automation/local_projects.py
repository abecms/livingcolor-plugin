"""Local (non-org) project registry under ~/.livingcolor/."""

from __future__ import annotations

import re
from typing import Any

from delivery_runtime.automation.config import (
    delivery_config_path,
    load_delivery_automation_config,
    save_delivery_project_config,
)
from delivery_runtime.persistence.paths import get_project_mapping_path
from delivery_runtime.readiness.project_mapping import load_project_mapping


def _project_name_from_mapping(key: str, mapping: dict[str, Any]) -> str:
    block = mapping.get(key) or mapping.get(key.upper()) or {}
    if isinstance(block, dict):
        return str(block.get("name") or block.get("project_name") or key).strip() or key
    return key


def _read_delivery_yaml() -> dict[str, Any]:
    path = delivery_config_path()
    if not path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _delivery_yaml_project() -> tuple[str, str] | None:
    """Return the explicitly configured local active project, if any."""
    raw = _read_delivery_yaml()
    project = raw.get("project")
    if isinstance(project, dict):
        key = str(project.get("key") or project.get("project_key") or "").strip().upper()
        if not key:
            return None
        name = str(project.get("name") or project.get("project_name") or key).strip() or key
        return key, name
    if isinstance(project, str) and project.strip():
        key = project.strip().upper()
        return key, key
    return None


def list_local_projects() -> list[dict[str, str]]:
    """Return personal/local projects from delivery.yaml and project_mapping.yaml."""
    mapping = load_project_mapping()
    by_key: dict[str, str] = {}

    explicit = _delivery_yaml_project()
    if explicit:
        by_key[explicit[0]] = explicit[1]

    for raw_key, raw_value in mapping.items():
        key = str(raw_key).strip().upper()
        if not key or not re.fullmatch(r"[A-Z][A-Z0-9]{1,19}", key):
            continue
        if key not in by_key:
            by_key[key] = _project_name_from_mapping(key, mapping if isinstance(mapping, dict) else {})

    return [
        {"jiraProjectKey": key, "projectName": name}
        for key, name in sorted(by_key.items())
    ]


def _write_project_mapping(mapping: dict[str, Any]) -> None:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to save local projects") from exc

    path = get_project_mapping_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(mapping, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _set_active_delivery_project(jira_project_key: str, project_name: str) -> None:
    key = jira_project_key.strip().upper()
    name = project_name.strip() or key
    path = delivery_config_path()
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("PyYAML is required to save local projects") from exc
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        existing = loaded if isinstance(loaded, dict) else {}

    project_block = existing.get("project")
    project_map = project_block if isinstance(project_block, dict) else {}
    project_map["key"] = key
    project_map["name"] = name
    existing["project"] = project_map

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to save local projects") from exc
    path.write_text(yaml.safe_dump(existing, sort_keys=False, allow_unicode=True), encoding="utf-8")


def register_local_project(jira_project_key: str, project_name: str) -> dict[str, str]:
    """Add or update a local project and make it the active delivery project."""
    key = jira_project_key.strip().upper()
    name = project_name.strip()
    if not key or not re.fullmatch(r"[A-Z][A-Z0-9]{1,19}", key):
        raise ValueError("Invalid Jira project key")
    if not name:
        raise ValueError("Project name is required")

    current = load_delivery_automation_config()
    mapping = load_project_mapping()
    if not isinstance(mapping, dict):
        mapping = {}
    current_key = current.project_key.strip().upper()
    if current_key and current_key != key:
        previous = mapping.get(current_key) or mapping.get(current_key.lower())
        previous_entry = previous if isinstance(previous, dict) else {}
        previous_entry.setdefault("name", current.project_name)
        mapping[current_key] = previous_entry
    block = mapping.get(key) or mapping.get(key.lower())
    entry = block if isinstance(block, dict) else {}
    entry["name"] = name
    mapping[key] = entry
    _write_project_mapping(mapping)
    _set_active_delivery_project(key, name)

    current = load_delivery_automation_config()
    save_delivery_project_config(
        capacity_days=current.sprint.capacity_days,
        duration_days=current.sprint.duration_days,
        communication_language=current.communication_language,
        project_key=key,
    )
    return {"jiraProjectKey": key, "projectName": name}


def remove_local_project(jira_project_key: str) -> None:
    """Remove a project from the personal/local registry after sharing to an org."""
    key = jira_project_key.strip().upper()
    if not key:
        raise ValueError("Project key is required")

    mapping = load_project_mapping()
    if not isinstance(mapping, dict):
        mapping = {}
    mapping_changed = False
    for candidate in list(mapping.keys()):
        if str(candidate).strip().upper() == key:
            mapping.pop(candidate, None)
            mapping_changed = True
    if mapping_changed:
        _write_project_mapping(mapping)

    raw = _read_delivery_yaml()
    project = raw.get("project")
    active_key: str | None = None
    if isinstance(project, dict):
        active_key = str(project.get("key") or project.get("project_key") or "").strip().upper() or None
    elif isinstance(project, str) and project.strip():
        active_key = project.strip().upper()

    if active_key == key:
        raw.pop("project", None)
        path = delivery_config_path()
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("PyYAML is required to save local projects") from exc
        if raw:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
        elif path.exists():
            path.unlink()

    remaining = list_local_projects()
    if remaining and active_key == key:
        first = remaining[0]
        _set_active_delivery_project(first["jiraProjectKey"], first["projectName"])


def activate_local_project(jira_project_key: str) -> dict[str, str]:
    """Switch the active local delivery project without changing mapping."""
    key = jira_project_key.strip().upper()
    if not key:
        raise ValueError("Project key is required")
    projects = {row["jiraProjectKey"]: row["projectName"] for row in list_local_projects()}
    if key not in projects:
        raise ValueError("Local project not found")
    _set_active_delivery_project(key, projects[key])
    return {"jiraProjectKey": key, "projectName": projects[key]}
