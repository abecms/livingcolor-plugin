"""Sprint reporter agent template renders and registers."""

from __future__ import annotations

import json
from pathlib import Path

TEMPLATES_DIR = (
    Path(__file__).resolve().parents[2] / "lc_server" / "agent_templates" / "v1"
)

VARIABLES = {
    "project_key": "BN",
    "project_name": "Bibliothèque Numérique",
    "language": "fr",
    "default_repo": "gitlab.com/org/service",
}


def test_reporter_template_renders_valid_manifest():
    from delivery_runtime.agents.schema import parse_agent_manifest
    from lc_server.provisioning.template_renderer import render_role_template

    rendered = render_role_template("reporter", variables=VARIABLES)
    manifest = parse_agent_manifest(rendered)
    assert manifest.role == "reporter"
    assert manifest.template_checksum.startswith("sha256:")
    assert manifest.runtime.type == "hermes"
    assert manifest.runtime.max_iterations == 8
    assert manifest.runtime.toolsets == ()
    assert "Sprint Reporter Agent" in manifest.prompt.system
    assert manifest.context["projectKey"] == "BN"
    skill_paths = {skill.path for skill in manifest.skills}
    assert "skills/delivery/agent-delivery-standards/SKILL.md" in skill_paths
    assert "skills/delivery/sprint-reporter/SKILL.md" in skill_paths


def test_manifest_declares_reporter_role():
    manifest = json.loads((TEMPLATES_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert "reporter" in manifest["roles"]
    assert manifest["version"] == "1.6.0"
