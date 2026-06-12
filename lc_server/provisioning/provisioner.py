"""Project automation provisioner — writes agent manifests and project state."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import yaml

from delivery_runtime.agents.paths import VALID_ROLES, get_agent_manifest_path, get_agents_dir, get_automation_state_path
from delivery_runtime.agents.registry import AgentManifestRegistry
from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.events.store import EventStore
from delivery_runtime.readiness.project_mapping import load_project_mapping
from delivery_runtime.readiness.project_settings import resolve_project_mcp_server
from lc_server.provisioning.gitlab_discovery import (
    GitLabDiscoveryResult,
    discover_gitlab_repos_for_project,
)
from lc_server.provisioning.prerequisites import require_provisioning_prerequisites
from lc_server.provisioning.template_renderer import get_template_version, render_role_template

logger = logging.getLogger(__name__)

EVENT_AUTOMATION_SETUP_STARTED = "AUTOMATION_SETUP_STARTED"
EVENT_AUTOMATION_SETUP_COMPLETED = "AUTOMATION_SETUP_COMPLETED"


@dataclass(frozen=True)
class ProvisionResult:
    status: str
    project_key: str
    agents_provisioned: list[str]
    repos_discovered: int
    default_repo: str | None
    template_version: str
    warnings: list[str]


def _normalize_project_key(project_key: str) -> str:
    key = (project_key or "").strip().upper()
    if not key:
        raise ValueError("project_key is required")
    return key


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_project_mapping(mapping: dict[str, Any]) -> None:
    try:
        import yaml as yaml_module
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to save project mapping") from exc

    from delivery_runtime.persistence.paths import get_project_mapping_path

    path = get_project_mapping_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml_module.safe_dump(mapping, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _merge_project_mapping_for_provision(
    *,
    project_key: str,
    project_name: str,
    default_repo: str | None,
    repos: list[dict[str, Any]],
) -> str | None:
    """Update mapping entry while preserving rules, integrations, and user default_repo."""
    key = _normalize_project_key(project_key)
    mapping = load_project_mapping()
    if not isinstance(mapping, dict):
        mapping = {}

    entry = mapping.get(key) or mapping.get(key.lower()) or {}
    if not isinstance(entry, dict):
        entry = {}

    preserved_rules = entry.get("rules")
    preserved_integrations = entry.get("integrations")
    existing_default = str(entry.get("default_repo") or "").strip()
    repo_paths = {str(item.get("path") or "").strip() for item in repos if isinstance(item, dict)}

    if existing_default:
        final_default = existing_default
    else:
        final_default = (default_repo or "").strip() or None

    entry["name"] = project_name
    if final_default:
        entry["default_repo"] = final_default
    entry["repos"] = list(repos)

    if preserved_rules is not None:
        entry["rules"] = preserved_rules
    if preserved_integrations is not None:
        entry["integrations"] = preserved_integrations

    mapping[key] = entry
    _write_project_mapping(mapping)
    return final_default


def _write_automation_state(
    *,
    project_key: str,
    template_version: str,
    provisioned_at: str,
    repos_discovered: int,
    default_repo: str | None,
) -> None:
    path = get_automation_state_path(project_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "projectKey": project_key,
        "status": "ready",
        "templateVersion": template_version,
        "provisionedAt": provisioned_at,
        "reposDiscovered": repos_discovered,
        "defaultRepo": default_repo or "",
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _agents_on_disk(project_key: str) -> list[str]:
    return [role for role in sorted(VALID_ROLES) if get_agent_manifest_path(project_key, role).is_file()]


class ProjectAutomationProvisioner:
    def __init__(self, events: EventStore | None = None) -> None:
        self.events = events or EventStore()
        self._registry = AgentManifestRegistry()

    def provision(self, project_key: str, *, force: bool = False) -> ProvisionResult:
        key = _normalize_project_key(project_key)
        template_version = get_template_version()

        if not force:
            existing = self._existing_ready_result(key, template_version)
            if existing is not None:
                return existing

        require_provisioning_prerequisites(key)
        self.events.append(
            event_type=EVENT_AUTOMATION_SETUP_STARTED,
            payload={"projectKey": key},
        )

        warnings: list[str] = []
        discovery = GitLabDiscoveryResult()
        gitlab_config = resolve_project_mcp_server(key, "gitlab")
        try:
            discovery = discover_gitlab_repos_for_project(key, gitlab_config)
            warnings.extend(discovery.warnings)
        except Exception as exc:
            logger.warning("GitLab discovery failed for %s: %s", key, exc)
            warnings.append(f"GitLab discovery failed: {exc}")

        config = load_delivery_automation_config(project_key=key)
        merged_default = _merge_project_mapping_for_provision(
            project_key=key,
            project_name=config.project_name,
            default_repo=discovery.default_repo,
            repos=discovery.repos,
        )
        if existing_default := merged_default:
            if existing_default not in {str(item.get("path") or "") for item in discovery.repos} and discovery.repos:
                warnings.append(
                    f"Using saved default repository {existing_default!r} (not matched by GitLab discovery heuristics)."
                )

        template_vars = {
            "project_key": key,
            "project_name": config.project_name,
            "language": config.communication_language,
            "default_repo": merged_default or discovery.default_repo or "",
        }

        agents_dir = get_agents_dir(key)
        agents_dir.mkdir(parents=True, exist_ok=True)
        agents_provisioned: list[str] = []
        for role in sorted(VALID_ROLES):
            rendered = render_role_template(role, variables=template_vars)
            get_agent_manifest_path(key, role).write_text(rendered, encoding="utf-8")
            agents_provisioned.append(role)

        provisioned_at = _utc_now_iso()
        _write_automation_state(
            project_key=key,
            template_version=template_version,
            provisioned_at=provisioned_at,
            repos_discovered=len(discovery.repos),
            default_repo=merged_default or discovery.default_repo,
        )

        result = ProvisionResult(
            status="ready",
            project_key=key,
            agents_provisioned=agents_provisioned,
            repos_discovered=len(discovery.repos),
            default_repo=merged_default or discovery.default_repo,
            template_version=template_version,
            warnings=warnings,
        )

        self.events.append(
            event_type=EVENT_AUTOMATION_SETUP_COMPLETED,
            payload={
                "projectKey": key,
                "templateVersion": template_version,
                "reposDiscovered": result.repos_discovered,
                "defaultRepo": result.default_repo,
                "warnings": warnings,
            },
        )
        return result

    def _existing_ready_result(self, project_key: str, template_version: str) -> ProvisionResult | None:
        state = self._registry.load_automation_state(project_key)
        if state is None:
            return None
        if state.status != "ready" or state.template_version != template_version:
            return None

        agents = _agents_on_disk(project_key)
        if len(agents) != len(VALID_ROLES):
            return None

        return ProvisionResult(
            status=state.status,
            project_key=project_key,
            agents_provisioned=agents,
            repos_discovered=state.repos_discovered,
            default_repo=state.default_repo,
            template_version=state.template_version,
            warnings=[],
        )
