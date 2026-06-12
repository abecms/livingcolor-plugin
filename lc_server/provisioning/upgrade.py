"""Auto-upgrade agent manifests when embedded templates are newer."""

from __future__ import annotations

import logging

from delivery_runtime.agents.paths import VALID_ROLES, get_agent_manifest_path, list_provisioned_project_keys
from delivery_runtime.agents.registry import AgentManifestRegistry
from delivery_runtime.agents.schema import AgentManifestError, parse_agent_manifest
from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.readiness.project_mapping import load_project_mapping
from lc_server.provisioning import template_renderer

logger = logging.getLogger(__name__)


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in version.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _is_newer_version(embedded: str, on_disk: str) -> bool:
    return _version_tuple(embedded) > _version_tuple(on_disk)


def _template_variables_for_project(project_key: str) -> dict[str, str]:
    config = load_delivery_automation_config(project_key=project_key)
    mapping = load_project_mapping()
    entry = mapping.get(project_key) or mapping.get(project_key.lower()) or {}
    if not isinstance(entry, dict):
        entry = {}
    default_repo = str(entry.get("default_repo") or "").strip()
    return {
        "project_key": project_key,
        "project_name": config.project_name,
        "language": config.communication_language,
        "default_repo": default_repo,
    }


def upgrade_all_project_manifests() -> list[str]:
    """Re-render non-manually-edited manifests when embedded template version is newer.

    Returns list of project keys upgraded.
    """
    embedded_version = template_renderer.get_template_version()
    upgraded_projects: list[str] = []
    registry = AgentManifestRegistry()

    for project_key in list_provisioned_project_keys():
        project_upgraded = False
        template_vars = _template_variables_for_project(project_key)
        state = registry.load_automation_state(project_key)
        state_version = state.template_version if state else ""

        for role in sorted(VALID_ROLES):
            path = get_agent_manifest_path(project_key, role)
            if not path.is_file():
                # A role added to the bundle after the project was provisioned has
                # no manifest on disk (and thus cannot be manually edited): render it.
                if _is_newer_version(embedded_version, state_version):
                    rendered = template_renderer.render_role_template(role, variables=template_vars)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(rendered, encoding="utf-8")
                    project_upgraded = True
                    logger.info(
                        "Rendered new %s/%s manifest at %s",
                        project_key,
                        role,
                        embedded_version,
                    )
                continue
            try:
                manifest = parse_agent_manifest(path.read_text(encoding="utf-8"))
            except (OSError, AgentManifestError) as exc:
                logger.warning("Skipping manifest upgrade for %s/%s: %s", project_key, role, exc)
                continue

            if manifest.manually_edited:
                continue
            if not _is_newer_version(embedded_version, manifest.template_version):
                continue

            rendered = template_renderer.render_role_template(role, variables=template_vars)
            path.write_text(rendered, encoding="utf-8")
            project_upgraded = True
            logger.info(
                "Upgraded %s/%s manifest from %s to %s",
                project_key,
                role,
                manifest.template_version,
                embedded_version,
            )

        if project_upgraded:
            upgraded_projects.append(project_key)

    return upgraded_projects
