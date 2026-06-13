from __future__ import annotations


def test_warm_skills_cache_command_reports_available_cache(monkeypatch, tmp_path, capsys):
    from lc_server.__main__ import main
    from lc_server.integrations.skills.cache import ExternalSkillsCacheResult

    registry_path = tmp_path / "skills-cache" / "livingcolor-skills" / "abc123" / "registry"
    cache_path = registry_path.parent

    result = ExternalSkillsCacheResult(
        available=True,
        registry_path=registry_path,
        cache_path=cache_path,
        source_ref="v0.1.0",
        resolved_commit="fdf1be62d61ef74b51d91ae81ed718350dce20d5",
    )

    monkeypatch.setattr(
        "lc_server.integrations.skills.resolver.warm_external_skills_cache",
        lambda: result,
    )

    exit_code = main(["warm-skills-cache"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "External skills cache available" in output
    assert str(registry_path) in output
    assert "fdf1be62d61ef74b51d91ae81ed718350dce20d5" in output


def test_warm_skills_cache_command_returns_nonzero_when_unavailable(monkeypatch, tmp_path, capsys):
    from lc_server.__main__ import main
    from lc_server.integrations.skills.cache import ExternalSkillsCacheResult

    registry_path = tmp_path / "skills-cache" / "livingcolor-skills" / "abc123" / "registry"
    cache_path = registry_path.parent

    result = ExternalSkillsCacheResult(
        available=False,
        registry_path=registry_path,
        cache_path=cache_path,
        source_ref="v0.1.0",
        resolved_commit="fdf1be62d61ef74b51d91ae81ed718350dce20d5",
        error="archive did not contain registry/",
    )

    monkeypatch.setattr(
        "lc_server.integrations.skills.resolver.warm_external_skills_cache",
        lambda: result,
    )

    exit_code = main(["warm-skills-cache"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "External skills cache unavailable" in output
    assert "archive did not contain registry/" in output
