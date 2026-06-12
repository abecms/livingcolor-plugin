"""Load LivingColor delivery automation configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lc_constants import get_livingcolor_home

DEFAULT_PROJECT_KEY = "BN"
DEFAULT_PROJECT_NAME = "Bibliothèque Numérique"

from delivery_runtime.communication.language import (  # noqa: E402
    DEFAULT_COMMUNICATION_LANGUAGE,
    get_clarification_comment_template,
    get_not_development_comment_template,
)

# Backward-compatible module-level templates (English). Prefer language-aware helpers.
CLARIFICATION_COMMENT_TEMPLATE = get_clarification_comment_template("en")
NOT_DEVELOPMENT_COMMENT_TEMPLATE = get_not_development_comment_template("en")


@dataclass(frozen=True)
class DailyAnalysisCronConfig:
    enabled: bool = True
    hour: int = 12
    minute: int = 0


@dataclass(frozen=True)
class SprintConfig:
    duration_days: int = 14
    capacity_days: float = 15.0


@dataclass(frozen=True)
class DeliveryAutomationConfig:
    project_key: str = DEFAULT_PROJECT_KEY
    project_name: str = DEFAULT_PROJECT_NAME
    communication_language: str = DEFAULT_COMMUNICATION_LANGUAGE
    daily_analysis_cron: DailyAnalysisCronConfig = DailyAnalysisCronConfig()
    sprint: SprintConfig = SprintConfig()
    ticket_scope: "TicketScopeConfig | None" = None


def _parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _config_file_candidates() -> list[Path]:
    home = get_livingcolor_home()
    return [
        home / "config" / "delivery.yaml",
        home / "config" / "delivery.yml",
        home / "config.yaml",
        home / "config.yml",
    ]


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _deep_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_active_project_key(merged: dict[str, Any], project_key: str | None = None) -> str:
    explicit = (project_key or os.environ.get("LIVINGCOLOR_PROJECT_KEY") or "").strip().upper()
    if explicit:
        return explicit

    project_block = merged.get("project")
    if isinstance(project_block, dict):
        key = str(project_block.get("key") or project_block.get("project_key") or "").strip().upper()
        if key:
            return key
    if isinstance(project_block, str) and project_block.strip():
        return project_block.strip().upper()
    return str(merged.get("project") or merged.get("project_key") or DEFAULT_PROJECT_KEY).upper()


def load_delivery_automation_config(*, project_key: str | None = None) -> DeliveryAutomationConfig:
    """Resolve automation config from env, then ~/.livingcolor config files."""
    merged: dict[str, Any] = {}
    for candidate in _config_file_candidates():
        if candidate.exists():
            merged = _deep_merge_dict(merged, _load_yaml_mapping(candidate))

    # Writable delivery settings always win over legacy root config files.
    delivery_path = delivery_config_path()
    if delivery_path.exists():
        merged = _deep_merge_dict(merged, _load_yaml_mapping(delivery_path))

    project_key_resolved = _resolve_active_project_key(merged, project_key)
    project_block = merged.get("project")
    project_name = DEFAULT_PROJECT_NAME
    if isinstance(project_block, dict):
        project_name = str(project_block.get("name") or project_block.get("project_name") or DEFAULT_PROJECT_NAME)
        if str(project_block.get("key") or project_block.get("project_key") or "").strip().upper() == project_key_resolved:
            project_name = str(project_block.get("name") or project_block.get("project_name") or project_name)
    elif isinstance(project_block, str) and project_block.strip().upper() == project_key_resolved:
        project_name = project_block.strip().upper()
    project_name = os.environ.get("LIVINGCOLOR_PROJECT_NAME", project_name).strip() or DEFAULT_PROJECT_NAME

    from delivery_runtime.readiness.project_mapping import load_project_mapping

    mapping = load_project_mapping()
    if isinstance(mapping, dict):
        mapped = mapping.get(project_key_resolved) or mapping.get(project_key_resolved.lower()) or {}
        if isinstance(mapped, dict):
            mapped_name = str(mapped.get("name") or mapped.get("project_name") or "").strip()
            if mapped_name:
                project_name = mapped_name

    automation = merged.get("automation")
    automation_map = automation if isinstance(automation, dict) else {}
    cron_map = automation_map.get("daily_analysis_cron")
    cron_map = cron_map if isinstance(cron_map, dict) else {}

    sprint_map = merged.get("sprint")
    sprint_map = sprint_map if isinstance(sprint_map, dict) else {}

    communication_map = merged.get("communication")
    communication_map = communication_map if isinstance(communication_map, dict) else {}
    from delivery_runtime.communication.language import normalize_communication_language

    cron_enabled = _parse_bool(
        os.environ.get("LIVINGCOLOR_DAILY_ANALYSIS_ENABLED"),
        _parse_bool(cron_map.get("enabled"), True),
    )
    cron_hour = _parse_int(os.environ.get("LIVINGCOLOR_DAILY_ANALYSIS_HOUR"), _parse_int(cron_map.get("hour"), 12))
    cron_minute = _parse_int(
        os.environ.get("LIVINGCOLOR_DAILY_ANALYSIS_MINUTE"),
        _parse_int(cron_map.get("minute"), 0),
    )

    from delivery_runtime.readiness.project_settings import (
        load_project_delivery_settings,
        mapping_has_delivery_settings,
    )
    from delivery_runtime.readiness.ticket_scope import default_ticket_scope, load_ticket_scope_for_project

    per_project = load_project_delivery_settings(project_key_resolved)
    active_key = _resolve_active_project_key(merged, None)
    has_mapping_settings = mapping_has_delivery_settings(project_key_resolved)

    if has_mapping_settings:
        sprint_duration = per_project.sprint_duration_days
        sprint_capacity = per_project.sprint_capacity_days
        communication_language = normalize_communication_language(per_project.communication_language)
    elif project_key_resolved == active_key:
        sprint_duration = _parse_int(sprint_map.get("duration_days"), per_project.sprint_duration_days)
        sprint_capacity = _parse_float(sprint_map.get("capacity_days"), per_project.sprint_capacity_days)
        communication_language = normalize_communication_language(
            os.environ.get("LIVINGCOLOR_COMMUNICATION_LANGUAGE")
            or communication_map.get("language")
            or (project_block.get("communication_language") if isinstance(project_block, dict) else None)
            or per_project.communication_language
        )
    else:
        sprint_duration = per_project.sprint_duration_days
        sprint_capacity = per_project.sprint_capacity_days
        communication_language = normalize_communication_language(per_project.communication_language)

    ticket_scope = load_ticket_scope_for_project(project_key_resolved) or default_ticket_scope()

    return DeliveryAutomationConfig(
        project_key=project_key_resolved,
        project_name=project_name,
        communication_language=communication_language,
        daily_analysis_cron=DailyAnalysisCronConfig(
            enabled=cron_enabled,
            hour=max(0, min(23, cron_hour)),
            minute=max(0, min(59, cron_minute)),
        ),
        sprint=SprintConfig(duration_days=max(1, sprint_duration), capacity_days=max(0.5, sprint_capacity)),
        ticket_scope=ticket_scope or default_ticket_scope(),
    )


def delivery_config_path() -> Path:
    """Primary writable delivery config file for LivingColor desktop."""
    path = get_livingcolor_home() / "config" / "delivery.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_delivery_project_config(
    *,
    capacity_days: float,
    duration_days: int,
    communication_language: str | None = None,
    ticket_scope: "TicketScopeConfig | None" = None,
    project_key: str | None = None,
) -> DeliveryAutomationConfig:
    """Persist delivery settings for one Jira project in project_mapping.yaml."""
    capacity_days = max(0.5, float(capacity_days))
    duration_days = max(1, int(duration_days))

    from delivery_runtime.communication.language import normalize_communication_language
    from delivery_runtime.readiness.project_settings import persist_project_delivery_settings
    from delivery_runtime.readiness.ticket_scope import default_ticket_scope

    current = load_delivery_automation_config(project_key=project_key)
    resolved_language = normalize_communication_language(
        communication_language if communication_language is not None else current.communication_language
    )
    resolved_scope = ticket_scope if ticket_scope is not None else current.ticket_scope or default_ticket_scope()
    target_key = (project_key or current.project_key or DEFAULT_PROJECT_KEY).strip().upper()

    persist_project_delivery_settings(
        project_key=target_key,
        duration_days=duration_days,
        capacity_days=capacity_days,
        communication_language=resolved_language,
        ticket_scope=resolved_scope,
    )

    path = delivery_config_path()
    existing: dict[str, Any] = _load_yaml_mapping(path) if path.exists() else {}
    project_block = existing.get("project")
    project_map = project_block if isinstance(project_block, dict) else {}
    project_map["key"] = target_key
    project_map.setdefault("name", current.project_name or DEFAULT_PROJECT_NAME)
    existing["project"] = project_map
    existing.pop("sprint", None)
    existing.pop("communication", None)
    existing.pop("ticket_scope", None)
    existing.pop("ticketScope", None)

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to save delivery project settings") from exc

    path.write_text(
        yaml.safe_dump(existing, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    config = load_delivery_automation_config(project_key=target_key)
    if communication_language is not None:
        previous_language = normalize_communication_language(current.communication_language)
        if resolved_language != previous_language:
            from delivery_runtime.pm_inbox.daily_pipeline import refresh_project_communications

            refresh_project_communications(project_key=config.project_key)
    from delivery_runtime.pm_inbox.sprint_selection import build_selected_sprint_payload, persist_selected_sprint

    sprint_payload = build_selected_sprint_payload(project_key=config.project_key)
    persist_selected_sprint(project_key=config.project_key, payload=sprint_payload)
    return config
