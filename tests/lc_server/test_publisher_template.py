"""Publisher agent template renders and registers."""

from __future__ import annotations

import json
from pathlib import Path

TEMPLATES_DIR = (
    Path(__file__).resolve().parents[2] / "lc_server" / "agent_templates" / "v1"
)

VARIABLES = {
    "project_key": "TVP",
    "project_name": "TV5",
    "language": "fr",
    "default_repo": "group/tv5-front",
}


def test_publisher_template_renders_valid_manifest():
    from delivery_runtime.agents.schema import parse_agent_manifest
    from lc_server.provisioning.template_renderer import render_role_template

    rendered = render_role_template("publisher", variables=VARIABLES)
    manifest = parse_agent_manifest(rendered)
    assert manifest.role == "publisher"
    assert manifest.template_checksum.startswith("sha256:")
    assert manifest.runtime.type == "hermes"
    assert manifest.runtime.max_iterations == 16
    assert "terminal" in manifest.runtime.toolsets
    assert "file" not in manifest.runtime.toolsets
    assert manifest.runtime.model is None
    assert manifest.runtime.provider is None
    assert "LivingColor Publisher Agent" in manifest.prompt.system
    assert manifest.context["projectKey"] == "TVP"
    skill_paths = {skill.path for skill in manifest.skills}
    assert "skills/delivery/agent-delivery-standards/SKILL.md" in skill_paths
    assert "skills/delivery/agent-mr-publisher/SKILL.md" in skill_paths


def test_publisher_skill_file_exists():
    import pytest

    skill_path = (
        TEMPLATES_DIR.parents[2] / "skills" / "delivery" / "agent-mr-publisher" / "SKILL.md"
    )
    if not skill_path.is_file():
        pytest.skip("LivingColor delivery skills are not bundled in the plugin yet")
    assert skill_path.is_file()


def test_manifest_declares_publisher_role():
    manifest = json.loads((TEMPLATES_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert "publisher" in manifest["roles"]
