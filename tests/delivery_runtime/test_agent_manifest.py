from pathlib import Path

import pytest


@pytest.fixture
def livingcolor_home(tmp_path, monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_HOME", str(tmp_path))
    return tmp_path


def test_project_agent_manifest_path(livingcolor_home):
    from delivery_runtime.agents.paths import get_agent_manifest_path

    path = get_agent_manifest_path("BN", "developer")
    assert path == livingcolor_home / "projects" / "BN" / "agents" / "developer.yaml"


def test_automation_state_path(livingcolor_home):
    from delivery_runtime.agents.paths import get_automation_state_path

    path = get_automation_state_path("BN")
    assert path == livingcolor_home / "projects" / "BN" / "automation.yaml"


DEVELOPER_FIXTURE = """
apiVersion: livingcolor.dev/v1
kind: AgentManifest
role: developer
templateVersion: "1.0.0"
templateChecksum: "sha256:deadbeef"
manuallyEdited: false
runtime:
  type: hermes
  maxIterations: 60
  toolsets: [file, terminal]
identity:
  displayName: Developer Agent
  platform: livingcolor-delivery
prompt:
  system: |
    You are the LivingColor Developer Agent.
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


def test_parse_valid_developer_manifest():
    from delivery_runtime.agents.schema import parse_agent_manifest

    manifest = parse_agent_manifest(DEVELOPER_FIXTURE)
    assert manifest.role == "developer"
    assert manifest.runtime.type == "hermes"
    assert manifest.runtime.toolsets == ("file", "terminal")
    assert manifest.runtime.model is None
    assert manifest.runtime.provider is None
    assert manifest.prompt.rules[0].id == "workspace-confinement"


def test_parse_developer_manifest_with_model_fields():
    from delivery_runtime.agents.schema import parse_agent_manifest

    fixture = DEVELOPER_FIXTURE.replace(
        "  toolsets: [file, terminal]",
        "  toolsets: [file, terminal, skills]\n  provider: openrouter\n  model: deepseek/deepseek-v4-pro",
    )
    manifest = parse_agent_manifest(fixture)
    assert manifest.runtime.model == "deepseek/deepseek-v4-pro"
    assert manifest.runtime.provider == "openrouter"


def test_parse_rejects_invalid_api_version():
    from delivery_runtime.agents.schema import AgentManifestError, parse_agent_manifest

    bad = DEVELOPER_FIXTURE.replace("livingcolor.dev/v1", "livingcolor.dev/v99")
    with pytest.raises(AgentManifestError, match="apiVersion"):
        parse_agent_manifest(bad)


def test_render_system_prompt_includes_rules():
    from delivery_runtime.agents.schema import parse_agent_manifest

    manifest = parse_agent_manifest(DEVELOPER_FIXTURE)
    rendered = manifest.render_system_prompt()
    assert "LivingColor Developer Agent" in rendered
    assert "## Rule: workspace-confinement" in rendered
    assert "Stay inside the workspace." in rendered


def test_registry_loads_manifest_from_disk(livingcolor_home):
    from delivery_runtime.agents.paths import get_agent_manifest_path, get_automation_state_path
    from delivery_runtime.agents.registry import AgentManifestRegistry

    project_key = "BN"
    agents_dir = get_agent_manifest_path(project_key, "developer").parent
    agents_dir.mkdir(parents=True)
    get_agent_manifest_path(project_key, "developer").write_text(DEVELOPER_FIXTURE, encoding="utf-8")
    get_automation_state_path(project_key).write_text(
        "projectKey: BN\nstatus: ready\ntemplateVersion: '1.0.0'\n",
        encoding="utf-8",
    )

    registry = AgentManifestRegistry()
    assert registry.is_automation_ready(project_key) is True
    manifest = registry.get(project_key, "developer")
    assert manifest is not None
    assert manifest.role == "developer"


def test_registry_returns_none_when_not_provisioned(livingcolor_home):
    from delivery_runtime.agents.registry import AgentManifestRegistry

    registry = AgentManifestRegistry()
    assert registry.is_automation_ready("ZZ") is False
    assert registry.get("ZZ", "developer") is None
