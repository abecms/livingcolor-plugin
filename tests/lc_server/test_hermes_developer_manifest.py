"""Tests for manifest-aware Hermes developer agent configuration."""

from __future__ import annotations

import pytest

DEVELOPER_FIXTURE = """
apiVersion: livingcolor.dev/v1
kind: AgentManifest
role: developer
templateVersion: "1.0.0"
templateChecksum: "sha256:deadbeef"
manuallyEdited: false
runtime:
  type: hermes
  maxIterations: 42
  toolsets: [file, terminal, search]
identity:
  displayName: Developer Agent
  platform: livingcolor-delivery-custom
prompt:
  system: |
    You are the Custom LivingColor Developer Agent.
  rules:
    - id: workspace-confinement
      content: Stay inside the workspace.
skills:
  - path: skills/delivery/developer-workspace/SKILL.md
mcp:
  inherit: project
  additional: []
context:
  communicationLanguage: fr
  projectKey: BN
"""


def _provision_developer_manifest(livingcolor_home, *, project_key: str = "BN") -> None:
    from delivery_runtime.agents.paths import get_agent_manifest_path, get_automation_state_path

    agents_dir = get_agent_manifest_path(project_key, "developer").parent
    agents_dir.mkdir(parents=True)
    get_agent_manifest_path(project_key, "developer").write_text(DEVELOPER_FIXTURE, encoding="utf-8")
    get_automation_state_path(project_key).write_text(
        f"projectKey: {project_key}\nstatus: ready\ntemplateVersion: '1.0.0'\n",
        encoding="utf-8",
    )


def test_resolve_developer_manifest_returns_manifest_when_automation_ready(livingcolor_home):
    from delivery_runtime.agents.registry import AgentManifestRegistry
    from lc_server.agent_bridge.hermes_developer import _resolve_developer_manifest

    _provision_developer_manifest(livingcolor_home)
    registry = AgentManifestRegistry()

    manifest = _resolve_developer_manifest("BN", registry=registry)

    assert manifest is not None
    assert manifest.role == "developer"
    assert manifest.runtime.toolsets == ("file", "terminal", "search")


def test_resolve_developer_manifest_falls_back_when_not_provisioned(livingcolor_home):
    from delivery_runtime.agents.registry import AgentManifestRegistry
    from lc_server.agent_bridge.hermes_developer import (
        DEVELOPER_SYSTEM_PROMPT,
        DEVELOPER_TOOLSETS,
        _developer_runtime_config,
        _resolve_developer_manifest,
    )

    registry = AgentManifestRegistry()

    assert _resolve_developer_manifest("ZZ", registry=registry) is None

    system_prompt, toolsets, max_iterations, platform = _developer_runtime_config(
        "ZZ",
        default_max_iterations=60,
        registry=registry,
    )
    assert system_prompt == DEVELOPER_SYSTEM_PROMPT
    assert toolsets == list(DEVELOPER_TOOLSETS)
    assert max_iterations == 60
    assert platform == "livingcolor-delivery"


def test_developer_runtime_config_uses_manifest_prompt_and_toolsets(livingcolor_home):
    from delivery_runtime.agents.registry import AgentManifestRegistry
    from lc_server.agent_bridge.hermes_developer import _developer_runtime_config

    _provision_developer_manifest(livingcolor_home)
    registry = AgentManifestRegistry()

    system_prompt, toolsets, max_iterations, platform = _developer_runtime_config(
        "BN",
        default_max_iterations=60,
        registry=registry,
    )

    assert "Custom LivingColor Developer Agent" in system_prompt
    assert "## Rule: workspace-confinement" in system_prompt
    assert toolsets == ["file", "terminal", "search"]
    assert max_iterations == 42
    assert platform == "livingcolor-delivery-custom"


def test_developer_template_has_no_hardcoded_provider():
    from lc_server.provisioning.template_renderer import render_role_template

    rendered = render_role_template(
        "developer",
        variables={
            "project_key": "TEST",
            "project_name": "Test",
            "language": "en",
            "default_repo": "group/test-app",
        },
    )
    assert "provider: openrouter" not in rendered
    assert "model: deepseek" not in rendered
