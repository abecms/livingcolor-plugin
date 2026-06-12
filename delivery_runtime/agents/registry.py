from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from delivery_runtime.agents.paths import (
    VALID_ROLES,
    get_agent_manifest_path,
    get_automation_state_path,
)
from delivery_runtime.agents.schema import AgentManifest, AgentManifestError, parse_agent_manifest

logger = logging.getLogger(__name__)


@dataclass
class AutomationState:
    project_key: str
    status: str
    template_version: str
    provisioned_at: str | None = None
    repos_discovered: int = 0
    default_repo: str | None = None


class AgentManifestRegistry:
    def __init__(self) -> None:
        self._manifest_cache: dict[tuple[str, str], AgentManifest] = {}
        self._mtime_cache: dict[Path, float] = {}

    def is_automation_ready(self, project_key: str) -> bool:
        state = self.load_automation_state(project_key)
        return state is not None and state.status == "ready"

    def load_automation_state(self, project_key: str) -> AutomationState | None:
        path = get_automation_state_path(project_key)
        if not path.is_file():
            return None
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except OSError:
            return None
        if not isinstance(loaded, dict):
            return None
        status = str(loaded.get("status") or "").strip()
        return AutomationState(
            project_key=str(loaded.get("projectKey") or project_key).strip().upper(),
            status=status,
            template_version=str(loaded.get("templateVersion") or "").strip(),
            provisioned_at=str(loaded.get("provisionedAt") or "").strip() or None,
            repos_discovered=int(loaded.get("reposDiscovered") or 0),
            default_repo=str(loaded.get("defaultRepo") or "").strip() or None,
        )

    def reload_if_changed(self, project_key: str) -> None:
        key = project_key.strip().upper()
        for role in VALID_ROLES:
            path = get_agent_manifest_path(key, role)
            if not path.is_file():
                self._manifest_cache.pop((key, role), None)
                self._mtime_cache.pop(path, None)
                continue
            mtime = path.stat().st_mtime
            if self._mtime_cache.get(path) != mtime:
                self._mtime_cache[path] = mtime
                self._manifest_cache.pop((key, role), None)

    def get(self, project_key: str, role: str) -> AgentManifest | None:
        key = project_key.strip().upper()
        normalized_role = role.strip().lower()
        self.reload_if_changed(key)
        cache_key = (key, normalized_role)
        if cache_key in self._manifest_cache:
            return self._manifest_cache[cache_key]

        path = get_agent_manifest_path(key, normalized_role)
        if not path.is_file():
            return None
        try:
            manifest = parse_agent_manifest(path.read_text(encoding="utf-8"))
        except (OSError, AgentManifestError) as exc:
            logger.warning("Invalid manifest %s: %s", path, exc)
            return None
        self._manifest_cache[cache_key] = manifest
        return manifest
