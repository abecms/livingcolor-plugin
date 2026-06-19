from __future__ import annotations

from pathlib import Path

import yaml


def test_ensure_livingcolor_pm_profile_bootstraps_tree(tmp_path, monkeypatch):
    from lc_server.integrations import livingcolor_pm_profile as module

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        yaml.safe_dump({"model": {"default": "test/model", "provider": "openrouter"}}),
        encoding="utf-8",
    )
    (hermes_home / ".env").write_text("OPENROUTER_API_KEY=secret\n", encoding="utf-8")

    skill_source = tmp_path / "plugin" / "skills" / "productivity" / "livingcolor-pm"
    skill_source.mkdir(parents=True)
    (skill_source / "SKILL.md").write_text("---\nname: livingcolor-pm\n---\n", encoding="utf-8")

    plugin_source = hermes_home / "plugins" / "livingcolor"
    plugin_source.mkdir(parents=True)
    (plugin_source / "plugin.yaml").write_text("name: livingcolor\n", encoding="utf-8")

    monkeypatch.setattr(module, "_hermes_home", lambda: hermes_home)
    monkeypatch.setattr(module, "_root_hermes_plugins_dir", lambda: hermes_home / "plugins")
    monkeypatch.setattr(module, "_plugin_root", lambda: tmp_path / "plugin")
    monkeypatch.setattr(module, "_seed_pm_skill", lambda _dir: None)

    profile_dir = module.ensure_livingcolor_pm_profile()

    assert profile_dir.is_dir()
    assert (profile_dir / ".no-bundled-skills").is_file()
    assert (profile_dir / "config.yaml").is_file()
    assert (profile_dir / ".env").is_file()
    config = yaml.safe_load((profile_dir / "config.yaml").read_text(encoding="utf-8"))
    assert config["display"]["tui_auto_resume_recent"] is False
    assert "livingcolor" in config["plugins"]["enabled"]
    assert config["platform_toolsets"]["tui"] == ["livingcolor"]
    assert config["model"]["default"] == "test/model"
    env_text = (profile_dir / ".env").read_text(encoding="utf-8")
    assert "HERMES_TUI_TOOLSETS=livingcolor" in env_text
    link = profile_dir / "plugins" / "livingcolor"
    assert link.is_symlink()
    assert link.resolve().name == "livingcolor"


def test_livingcolor_pm_profile_exists(tmp_path, monkeypatch):
    from lc_server.integrations import livingcolor_pm_profile as module

    hermes_home = tmp_path / ".hermes"
    monkeypatch.setattr(module, "_hermes_home", lambda: hermes_home)
    assert module.livingcolor_pm_profile_exists() is False
    module.ensure_livingcolor_pm_profile()
    assert module.livingcolor_pm_profile_exists() is True
