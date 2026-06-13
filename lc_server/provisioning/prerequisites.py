"""Prerequisites validation for project automation provisioning."""

from __future__ import annotations

from typing import Any

from delivery_runtime.readiness.project_settings import (
    load_project_vcs_provider,
    resolve_project_mcp_server,
)
from lc_server.model_defaults import is_delivery_llm_available
from lc_server.provisioning.errors import ProvisionError

_JIRA_MCP_CODE = "jira_mcp"
_GITLAB_MCP_CODE = "gitlab_mcp"
_GITHUB_MCP_CODE = "github_mcp"
_LLM_MODEL_CODE = "llm_model"


def _provider_mcp_code(provider: str) -> tuple[str, str]:
    if provider == "github":
        return "github", _GITHUB_MCP_CODE
    return "gitlab", _GITLAB_MCP_CODE


def _is_mcp_server_configured(config: dict[str, Any] | None) -> bool:
    if not isinstance(config, dict) or not config:
        return False

    url = config.get("url")
    if isinstance(url, str) and url.strip():
        return True

    env = config.get("env")
    if isinstance(env, dict):
        for value in env.values():
            if value is not None and str(value).strip():
                return True

    return False


def check_provisioning_prerequisites(project_key: str) -> list[str]:
    """Return list of missing prerequisite codes. Empty = OK.

    Codes: jira_mcp, gitlab_mcp, github_mcp, llm_model
    """
    missing: list[str] = []

    if not _is_mcp_server_configured(resolve_project_mcp_server(project_key, "jira")):
        missing.append(_JIRA_MCP_CODE)

    provider = load_project_vcs_provider(project_key)
    provider_server, provider_code = _provider_mcp_code(provider)
    if not _is_mcp_server_configured(resolve_project_mcp_server(project_key, provider_server)):
        missing.append(provider_code)

    if not is_delivery_llm_available():
        missing.append(_LLM_MODEL_CODE)

    return missing


def require_provisioning_prerequisites(project_key: str) -> None:
    """Raise ProvisionError if any missing."""
    missing = check_provisioning_prerequisites(project_key)
    if missing:
        raise ProvisionError(missing)
