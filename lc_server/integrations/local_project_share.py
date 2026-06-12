"""Export local ~/.livingcolor project data for org sharing."""

from __future__ import annotations

from typing import Any

from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.automation.local_projects import list_local_projects
from delivery_runtime.readiness.project_mapping import load_project_mapping


def build_local_project_share_payload(jira_project_key: str) -> dict[str, Any]:
    key = jira_project_key.strip().upper()
    if not key:
        raise ValueError("Project key is required")

    catalog = {row["jiraProjectKey"]: row["projectName"] for row in list_local_projects()}
    if key not in catalog:
        raise ValueError("Local project not found")

    mapping_root = load_project_mapping()
    block = {}
    if isinstance(mapping_root, dict):
        block = mapping_root.get(key) or mapping_root.get(key.lower()) or {}
    if not isinstance(block, dict):
        block = {}

    mapping_copy = {
        field: value
        for field, value in block.items()
        if field not in {"name", "project_name"} and value is not None
    }

    from delivery_runtime.readiness.project_settings import serialize_delivery_settings_for_share
    from delivery_runtime.readiness.ticket_scope import load_ticket_scope_for_project

    delivery_settings = serialize_delivery_settings_for_share(
        key,
        ticket_scope=load_ticket_scope_for_project(key),
    )

    return {
        "jiraProjectKey": key,
        "projectName": catalog[key],
        "mapping": mapping_copy or None,
        "deliverySettings": delivery_settings,
    }
