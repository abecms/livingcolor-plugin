from __future__ import annotations


RESOLVED_COMMIT = "fdf1be62d61ef74b51d91ae81ed718350dce20d5"


def _write_registry(root):
    bundle_dir = root / "bundles" / "code-review-pipeline"
    bundle_dir.mkdir(parents=True)
    bundle_dir.joinpath("bundle.yaml").write_text(
        "name: code-review-pipeline\nskills:\n  - ticket-analyst\n  - code-architect\n",
        encoding="utf-8",
    )
    for name, prompt in {
        "ticket-analyst": "# Ticket Analyst\nAssess readiness.",
        "code-architect": "# Code Architect\nAssess architecture.",
    }.items():
        skill_dir = root / name
        skill_dir.mkdir()
        skill_dir.joinpath("skill.yaml").write_text(f"name: {name}\nversion: 2.0.0\n", encoding="utf-8")
        skill_dir.joinpath("prompt.md").write_text(prompt, encoding="utf-8")


def test_resolve_valid_external_bundle(tmp_path):
    from lc_server.integrations.skills.registry import resolve_external_bundle

    registry = tmp_path / "registry"
    registry.mkdir()
    _write_registry(registry)

    bundle = resolve_external_bundle(
        registry_path=registry,
        bundle_name="code-review-pipeline",
        required_skills=("ticket-analyst", "code-architect"),
        resolved_commit=RESOLVED_COMMIT,
    )

    assert bundle.available is True
    assert bundle.bundle_name == "code-review-pipeline"
    assert [skill.name for skill in bundle.skills] == ["ticket-analyst", "code-architect"]
    assert bundle.skills[0].prompt.startswith("# Ticket Analyst")


def test_resolve_external_bundle_reports_missing_skill(tmp_path):
    from lc_server.integrations.skills.registry import resolve_external_bundle

    registry = tmp_path / "registry"
    registry.mkdir()
    _write_registry(registry)

    bundle = resolve_external_bundle(
        registry_path=registry,
        bundle_name="code-review-pipeline",
        required_skills=("ticket-analyst", "security-auditor"),
        resolved_commit=RESOLVED_COMMIT,
    )

    assert bundle.available is False
    assert "security-auditor" in bundle.error


def test_resolve_external_bundle_rejects_non_string_skill_item(tmp_path):
    from lc_server.integrations.skills.registry import resolve_external_bundle

    registry = tmp_path / "registry"
    registry.mkdir()
    _write_registry(registry)
    (registry / "bundles" / "code-review-pipeline" / "bundle.yaml").write_text(
        "name: code-review-pipeline\nskills:\n  - ticket-analyst\n  - 123\n",
        encoding="utf-8",
    )

    bundle = resolve_external_bundle(
        registry_path=registry,
        bundle_name="code-review-pipeline",
        required_skills=("ticket-analyst",),
        resolved_commit=RESOLVED_COMMIT,
    )

    assert bundle.available is False
    assert "skills" in bundle.error


def test_resolve_external_bundle_reports_invalid_bundle_yaml(tmp_path):
    from lc_server.integrations.skills.registry import resolve_external_bundle

    registry = tmp_path / "registry"
    bundle_dir = registry / "bundles" / "code-review-pipeline"
    bundle_dir.mkdir(parents=True)
    bundle_dir.joinpath("bundle.yaml").write_text("skills: [", encoding="utf-8")

    bundle = resolve_external_bundle(
        registry_path=registry,
        bundle_name="code-review-pipeline",
        required_skills=("ticket-analyst",),
        resolved_commit=RESOLVED_COMMIT,
    )

    assert bundle.available is False
    assert "invalid bundle yaml" in bundle.error


def test_resolve_external_bundle_reports_missing_prompt(tmp_path):
    from lc_server.integrations.skills.registry import resolve_external_bundle

    registry = tmp_path / "registry"
    registry.mkdir()
    _write_registry(registry)
    (registry / "ticket-analyst" / "prompt.md").unlink()

    bundle = resolve_external_bundle(
        registry_path=registry,
        bundle_name="code-review-pipeline",
        required_skills=("ticket-analyst",),
        resolved_commit=RESOLVED_COMMIT,
    )

    assert bundle.available is False
    assert "skill prompt not found: ticket-analyst" in bundle.error


def test_resolve_external_bundle_reports_skill_name_mismatch(tmp_path):
    from lc_server.integrations.skills.registry import resolve_external_bundle

    registry = tmp_path / "registry"
    registry.mkdir()
    _write_registry(registry)
    (registry / "ticket-analyst" / "skill.yaml").write_text(
        "name: other-skill\nversion: 2.0.0\n",
        encoding="utf-8",
    )

    bundle = resolve_external_bundle(
        registry_path=registry,
        bundle_name="code-review-pipeline",
        required_skills=("ticket-analyst",),
        resolved_commit=RESOLVED_COMMIT,
    )

    assert bundle.available is False
    assert "skill name mismatch" in bundle.error


def test_guidance_renders_selected_skills(tmp_path):
    from lc_server.integrations.skills.guidance import render_external_guidance
    from lc_server.integrations.skills.registry import resolve_external_bundle

    registry = tmp_path / "registry"
    registry.mkdir()
    _write_registry(registry)
    bundle = resolve_external_bundle(
        registry_path=registry,
        bundle_name="code-review-pipeline",
        required_skills=("ticket-analyst", "code-architect"),
        resolved_commit=RESOLVED_COMMIT,
    )

    guidance = render_external_guidance(bundle, skill_names=("code-architect",))

    assert "External LivingColor Skills Guidance" in guidance
    assert f"Source commit: {RESOLVED_COMMIT}" in guidance
    assert "# Code Architect" in guidance
    assert "# Ticket Analyst" not in guidance


def test_guidance_returns_empty_string_for_unavailable_bundle(tmp_path):
    from lc_server.integrations.skills.guidance import render_external_guidance
    from lc_server.integrations.skills.registry import resolve_external_bundle

    registry = tmp_path / "registry"
    registry.mkdir()

    bundle = resolve_external_bundle(
        registry_path=registry,
        bundle_name="code-review-pipeline",
        required_skills=("ticket-analyst",),
        resolved_commit=RESOLVED_COMMIT,
    )

    assert render_external_guidance(bundle, skill_names=("ticket-analyst",)) == ""
