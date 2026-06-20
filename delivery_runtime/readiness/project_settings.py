"""Per-project delivery settings stored in project_mapping.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from delivery_runtime.communication.language import DEFAULT_COMMUNICATION_LANGUAGE, normalize_communication_language
from delivery_runtime.readiness.project_mapping import load_project_mapping
from delivery_runtime.readiness.ticket_scope import (
    TicketScopeConfig,
    default_ticket_scope,
    parse_ticket_scope,
    persist_ticket_scope_for_project,
    serialize_ticket_scope,
)

_DEFAULT_SPRINT_DURATION_DAYS = 14
_DEFAULT_SPRINT_CAPACITY_DAYS = 15.0
_DEFAULT_SPRINT_START_WEEKDAY = 1  # ISO: Monday
_INTEGRATION_MCP_KEY = "mcp_servers"


@dataclass(frozen=True)
class ProjectDeliverySettings:
    sprint_duration_days: int = _DEFAULT_SPRINT_DURATION_DAYS
    sprint_capacity_days: float = _DEFAULT_SPRINT_CAPACITY_DAYS
    sprint_start_weekday: int = _DEFAULT_SPRINT_START_WEEKDAY
    communication_language: str = DEFAULT_COMMUNICATION_LANGUAGE


@dataclass(frozen=True)
class BillingSettings:
    stripe_customer_id: str | None = None
    daily_rate_cents: int | None = None
    currency: str = "eur"
    invoice_mode: str = "draft"
    approval_required: bool = False
    max_invoice_cents: int | None = None


def normalize_sprint_start_weekday(value: Any) -> int:
    try:
        weekday = int(value)
    except (TypeError, ValueError):
        weekday = _DEFAULT_SPRINT_START_WEEKDAY
    return max(1, min(7, weekday))


def _normalize_project_key(project_key: str) -> str:
    return (project_key or "").strip().upper()


def _mapping_entry(project_key: str, mapping: dict[str, Any] | None = None) -> dict[str, Any]:
    root = mapping if mapping is not None else load_project_mapping()
    if not isinstance(root, dict):
        return {}
    block = root.get(project_key) or root.get(project_key.lower()) or {}
    return block if isinstance(block, dict) else {}


def _write_project_mapping(mapping: dict[str, Any]) -> None:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to save project settings") from exc

    from delivery_runtime.persistence.paths import get_project_mapping_path

    path = get_project_mapping_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(mapping, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _upsert_mapping_entry(project_key: str, updater) -> dict[str, Any]:
    key = _normalize_project_key(project_key)
    if not key:
        raise ValueError("project_key is required")

    mapping = load_project_mapping()
    if not isinstance(mapping, dict):
        mapping = {}
    entry = _mapping_entry(key, mapping)
    updater(entry)
    mapping[key] = entry
    _write_project_mapping(mapping)
    return entry


def mapping_has_delivery_settings(project_key: str) -> bool:
    entry = _mapping_entry(_normalize_project_key(project_key))
    sprint = entry.get("sprint")
    return isinstance(sprint, dict) and (
        sprint.get("duration_days") is not None or sprint.get("capacity_days") is not None
    )


def load_project_delivery_settings(project_key: str) -> ProjectDeliverySettings:
    key = _normalize_project_key(project_key)
    if not key:
        return ProjectDeliverySettings()

    entry = _mapping_entry(key)
    sprint = entry.get("sprint")
    sprint_map = sprint if isinstance(sprint, dict) else {}

    duration_raw = sprint_map.get("duration_days")
    capacity_raw = sprint_map.get("capacity_days")
    start_weekday_raw = (
        sprint_map.get("start_weekday")
        or sprint_map.get("startWeekday")
        or sprint_map.get("reset_weekday")
        or sprint_map.get("resetWeekday")
    )
    language_raw = entry.get("communication_language") or entry.get("communicationLanguage")

    duration = _DEFAULT_SPRINT_DURATION_DAYS
    if duration_raw is not None:
        try:
            duration = max(1, int(duration_raw))
        except (TypeError, ValueError):
            pass

    capacity = _DEFAULT_SPRINT_CAPACITY_DAYS
    if capacity_raw is not None:
        try:
            capacity = max(0.5, float(capacity_raw))
        except (TypeError, ValueError):
            pass

    return ProjectDeliverySettings(
        sprint_duration_days=duration,
        sprint_capacity_days=capacity,
        sprint_start_weekday=normalize_sprint_start_weekday(start_weekday_raw),
        communication_language=normalize_communication_language(language_raw),
    )


def _normalize_optional_positive_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalize_billing_currency(value: Any) -> str:
    text = str(value or "eur").strip().lower()
    return text if len(text) == 3 and text.isalpha() else "eur"


def _normalize_invoice_mode(value: Any) -> str:
    text = str(value or "draft").strip().lower()
    return text if text in {"draft", "finalize"} else "draft"


def load_project_billing_settings(project_key: str) -> BillingSettings:
    from lc_server.integrations.plugin_billing import load_plugin_billing_settings

    return load_plugin_billing_settings()


def persist_project_billing_settings(
    *,
    project_key: str,
    stripe_customer_id: str | None,
    daily_rate_cents: int | None,
    currency: str = "eur",
    invoice_mode: str = "draft",
    approval_required: bool = False,
    max_invoice_cents: int | None = None,
) -> BillingSettings:
    from lc_server.integrations.plugin_billing import persist_plugin_billing_settings

    return persist_plugin_billing_settings(
        stripe_customer_id=stripe_customer_id,
        daily_rate_cents=daily_rate_cents,
        currency=currency,
        invoice_mode=invoice_mode,
        approval_required=approval_required,
        max_invoice_cents=max_invoice_cents,
    )


def persist_project_delivery_settings(
    *,
    project_key: str,
    duration_days: int,
    capacity_days: float,
    communication_language: str,
    start_weekday: int | None = None,
    ticket_scope: TicketScopeConfig | None = None,
) -> ProjectDeliverySettings:
    key = _normalize_project_key(project_key)
    if not key:
        raise ValueError("project_key is required")

    resolved_duration = max(1, int(duration_days))
    resolved_capacity = max(0.5, float(capacity_days))
    resolved_language = normalize_communication_language(communication_language)

    def _update(entry: dict[str, Any]) -> None:
        sprint = entry.get("sprint")
        sprint_map = dict(sprint) if isinstance(sprint, dict) else {}
        sprint_map["duration_days"] = resolved_duration
        sprint_map["capacity_days"] = resolved_capacity
        if start_weekday is not None:
            sprint_map["start_weekday"] = normalize_sprint_start_weekday(start_weekday)
        elif "start_weekday" not in sprint_map and "startWeekday" not in sprint_map:
            legacy = sprint_map.get("reset_weekday") or sprint_map.get("resetWeekday")
            sprint_map["start_weekday"] = normalize_sprint_start_weekday(legacy)
        entry["sprint"] = sprint_map
        entry["communication_language"] = resolved_language

    _upsert_mapping_entry(key, _update)

    scope = ticket_scope if ticket_scope is not None else default_ticket_scope()
    persist_ticket_scope_for_project(key, scope)

    current = load_project_delivery_settings(key)
    resolved_start_weekday = (
        normalize_sprint_start_weekday(start_weekday)
        if start_weekday is not None
        else current.sprint_start_weekday
    )

    return ProjectDeliverySettings(
        sprint_duration_days=resolved_duration,
        sprint_capacity_days=resolved_capacity,
        sprint_start_weekday=resolved_start_weekday,
        communication_language=resolved_language,
    )


def load_project_default_repo(project_key: str) -> str | None:
    entry = _mapping_entry(_normalize_project_key(project_key))
    raw = str(entry.get("default_repo") or "").strip()
    return raw or None


def load_project_integration_branch(project_key: str) -> str | None:
    """Return the configured GitLab MR target branch for a project, if set."""
    from delivery_runtime.readiness.project_mapping import resolve_configured_integration_branch

    return resolve_configured_integration_branch(_normalize_project_key(project_key))


def persist_project_integration_branch(project_key: str, integration_branch: str) -> str:
    key = _normalize_project_key(project_key)
    branch = (integration_branch or "").strip()
    if not branch:
        raise ValueError("integration_branch is required")

    def _update(entry: dict[str, Any]) -> None:
        entry["integration_branch"] = branch

    _upsert_mapping_entry(key, _update)
    return branch


def load_project_jira_project_key(project_key: str) -> str | None:
    """Return the linked Jira project key when it differs from the LivingColor project key."""
    entry = _mapping_entry(_normalize_project_key(project_key))
    raw = str(entry.get("jira_project_key") or entry.get("jiraProjectKey") or "").strip().upper()
    return raw or None


def resolve_jira_project_key(project_key: str) -> str:
    """Resolve the Jira project key used for scans and daily analysis."""
    key = _normalize_project_key(project_key)
    return load_project_jira_project_key(key) or key


def persist_project_jira_project_key(project_key: str, jira_project_key: str) -> str:
    key = _normalize_project_key(project_key)
    linked = _normalize_project_key(jira_project_key)
    if not linked:
        raise ValueError("jira_project_key is required")

    def _update(entry: dict[str, Any]) -> None:
        entry["jira_project_key"] = linked

    _upsert_mapping_entry(key, _update)
    return linked


def load_project_vcs_provider(project_key: str) -> str:
    """Return the configured VCS provider for a project; defaults to GitLab."""
    from lc_server.integrations.vcs.provider import normalize_vcs_provider

    entry = _mapping_entry(_normalize_project_key(project_key))
    return normalize_vcs_provider(entry.get("vcs"))


def persist_project_vcs_provider(project_key: str, vcs_provider: str) -> str:
    from lc_server.integrations.vcs.provider import normalize_vcs_provider

    key = _normalize_project_key(project_key)
    provider = normalize_vcs_provider(vcs_provider)

    def _update(entry: dict[str, Any]) -> None:
        entry["vcs"] = provider

    _upsert_mapping_entry(key, _update)
    return provider


def load_project_gitlab_repos(project_key: str) -> list[dict[str, Any]]:
    entry = _mapping_entry(_normalize_project_key(project_key))
    repos = entry.get("repos")
    if not isinstance(repos, list):
        return []
    out: list[dict[str, Any]] = []
    for item in repos:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        gitlab_id = item.get("gitlabId")
        out.append({"path": path, "gitlabId": gitlab_id})
    return out


def persist_project_default_repo(project_key: str, default_repo: str) -> str:
    key = _normalize_project_key(project_key)
    repo = (default_repo or "").strip()
    if not repo:
        raise ValueError("default_repo is required")

    def _update(entry: dict[str, Any]) -> None:
        entry["default_repo"] = repo

    _upsert_mapping_entry(key, _update)
    _sync_provisioned_default_repo(key, repo)
    return repo


def _patch_yaml_context_default_repo(path, default_repo: str) -> None:
    try:
        import yaml
    except ImportError:
        return

    if not path.is_file():
        return
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return
    if not isinstance(loaded, dict):
        return
    context = loaded.get("context")
    context_map = dict(context) if isinstance(context, dict) else {}
    context_map["defaultRepo"] = default_repo
    loaded["context"] = context_map
    path.write_text(yaml.safe_dump(loaded, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _patch_automation_state_default_repo(path, default_repo: str) -> None:
    try:
        import yaml
    except ImportError:
        return

    if not path.is_file():
        return
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return
    if not isinstance(loaded, dict):
        return
    loaded["defaultRepo"] = default_repo
    path.write_text(yaml.safe_dump(loaded, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _sync_provisioned_default_repo(project_key: str, default_repo: str) -> None:
    from delivery_runtime.agents.paths import VALID_ROLES, get_agent_manifest_path, get_automation_state_path

    for role in VALID_ROLES:
        _patch_yaml_context_default_repo(get_agent_manifest_path(project_key, role), default_repo)
    _patch_automation_state_default_repo(get_automation_state_path(project_key), default_repo)


def load_project_mcp_servers(project_key: str) -> dict[str, dict[str, Any]]:
    key = _normalize_project_key(project_key)
    if not key:
        return {}

    entry = _mapping_entry(key)
    integrations = entry.get("integrations")
    integrations_map = integrations if isinstance(integrations, dict) else {}
    stored = integrations_map.get(_INTEGRATION_MCP_KEY)
    if not isinstance(stored, dict):
        return {}

    out: dict[str, dict[str, Any]] = {}
    for name, config in stored.items():
        server_name = str(name).strip()
        if not server_name or not isinstance(config, dict):
            continue
        out[server_name] = dict(config)
    return out


def _resolve_global_mcp_server_name(server_name: str, servers: dict[str, Any]) -> str:
    canonical = str(server_name or "").strip().lower()
    try:
        from lc_server.integrations.mcp_server_resolver import (
            active_github_mcp_name,
            active_gitlab_mcp_name,
            active_jira_mcp_name,
        )
    except ImportError:
        return str(server_name or "").strip()

    if canonical == "jira":
        return active_jira_mcp_name(servers)
    if canonical == "gitlab":
        return active_gitlab_mcp_name(servers)
    if canonical == "github":
        return active_github_mcp_name(servers)
    return str(server_name or "").strip()


def resolve_project_mcp_server(project_key: str, server_name: str) -> dict[str, Any]:
    """Return MCP config saved on the project, falling back to global Hermes config."""
    stored = load_project_mcp_servers(project_key).get(server_name)
    if isinstance(stored, dict) and stored:
        return dict(stored)

    try:
        from lc_server.integrations.mcp_config_bridge import load_effective_mcp_servers

        servers = load_effective_mcp_servers()
        resolved_name = _resolve_global_mcp_server_name(server_name, servers)
        global_cfg = servers.get(resolved_name)
        if isinstance(global_cfg, dict) and global_cfg:
            return dict(global_cfg)
    except ImportError:
        pass

    return {}


def resolve_jira_browse_base_url(project_key: str) -> str | None:
    """Return the Jira site URL saved for a project, if any."""
    servers = load_project_mcp_servers(project_key)
    jira_cfg = servers.get("jira")
    if not isinstance(jira_cfg, dict):
        try:
            from hermes_cli.mcp_config import _get_mcp_servers
            from lc_server.integrations.mcp_server_resolver import active_jira_mcp_name

            global_servers = _get_mcp_servers()
            jira_cfg = global_servers.get(active_jira_mcp_name(global_servers))
        except ImportError:
            jira_cfg = None

    if not isinstance(jira_cfg, dict):
        return None

    env = jira_cfg.get("env")
    if not isinstance(env, dict):
        return None

    raw = str(env.get("JIRA_URL") or "").strip()
    if not raw:
        return None

    with_protocol = raw if raw.lower().startswith(("http://", "https://")) else f"https://{raw}"
    return with_protocol if with_protocol.endswith("/") else f"{with_protocol}/"


def persist_project_mcp_server(project_key: str, server_name: str, server_config: dict[str, Any]) -> None:
    key = _normalize_project_key(project_key)
    name = (server_name or "").strip()
    if not key or not name:
        raise ValueError("project_key and server_name are required")
    if not isinstance(server_config, dict):
        raise ValueError("server_config must be a mapping")

    def _update(entry: dict[str, Any]) -> None:
        integrations = entry.get("integrations")
        integrations_map = integrations if isinstance(integrations, dict) else {}
        stored = integrations_map.get(_INTEGRATION_MCP_KEY)
        stored_map = stored if isinstance(stored, dict) else {}
        stored_map[name] = dict(server_config)
        integrations_map[_INTEGRATION_MCP_KEY] = stored_map
        entry["integrations"] = integrations_map

    _upsert_mapping_entry(key, _update)


def serialize_delivery_settings_for_share(
    project_key: str,
    *,
    ticket_scope: TicketScopeConfig | None = None,
) -> dict[str, Any]:
    from delivery_runtime.automation.config import load_delivery_automation_config

    config = load_delivery_automation_config(project_key=project_key)
    scope = ticket_scope if ticket_scope is not None else config.ticket_scope or default_ticket_scope()
    return {
        "sprintDurationDays": config.sprint.duration_days,
        "sprintCapacityDays": config.sprint.capacity_days,
        "sprintStartWeekday": config.sprint.start_weekday,
        "communicationLanguage": config.communication_language,
        "ticketScope": serialize_ticket_scope(scope),
    }


def apply_shared_delivery_settings(project_key: str, payload: dict[str, Any] | None) -> None:
    if not isinstance(payload, dict):
        return
    key = _normalize_project_key(project_key)
    if not key:
        return

    duration = payload.get("sprintDurationDays")
    capacity = payload.get("sprintCapacityDays")
    start_weekday = payload.get("sprintStartWeekday") or payload.get("sprintResetWeekday")
    language = payload.get("communicationLanguage")
    scope_raw = payload.get("ticketScope")

    if duration is None and capacity is None and start_weekday is None and language is None and scope_raw is None:
        return

    current = load_project_delivery_settings(key)
    persist_project_delivery_settings(
        project_key=key,
        duration_days=int(duration) if duration is not None else current.sprint_duration_days,
        capacity_days=float(capacity) if capacity is not None else current.sprint_capacity_days,
        start_weekday=int(start_weekday) if start_weekday is not None else None,
        communication_language=str(language) if language is not None else current.communication_language,
        ticket_scope=parse_ticket_scope(scope_raw) if scope_raw is not None else None,
    )
