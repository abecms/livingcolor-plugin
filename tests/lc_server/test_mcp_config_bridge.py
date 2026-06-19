from __future__ import annotations

import yaml


def test_load_effective_mcp_servers_merges_root_when_profile_empty(tmp_path, monkeypatch):
    from lc_server.integrations import mcp_config_bridge as module

    root = tmp_path / ".hermes"
    profile = root / "profiles" / "livingcolor-pm"
    profile.mkdir(parents=True)
    (root / "config.yaml").write_text(
        yaml.safe_dump({"mcp_servers": {"Atlassian": {"command": "uvx", "env": {"JIRA_URL": "https://jira.example"}}}}),
        encoding="utf-8",
    )
    (profile / "config.yaml").write_text(yaml.safe_dump({}), encoding="utf-8")

    monkeypatch.setattr(module, "default_hermes_root", lambda: root)
    monkeypatch.setattr(
        "hermes_cli.mcp_config._get_mcp_servers",
        lambda: {},
    )

    servers = module.load_effective_mcp_servers()
    assert "Atlassian" in servers
    assert servers["Atlassian"]["env"]["JIRA_URL"] == "https://jira.example"


def test_profile_sync_copies_root_mcp_servers(tmp_path, monkeypatch):
    from lc_server.integrations import livingcolor_pm_profile as module

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "model": {"default": "test/model", "provider": "openrouter"},
                "mcp_servers": {"Atlassian": {"command": "uvx"}},
            }
        ),
        encoding="utf-8",
    )
    (hermes_home / ".env").write_text("OPENROUTER_API_KEY=secret\n", encoding="utf-8")

    plugin_source = hermes_home / "plugins" / "livingcolor"
    plugin_source.mkdir(parents=True)

    monkeypatch.setattr(module, "_hermes_home", lambda: hermes_home)
    monkeypatch.setattr("lc_server.integrations.mcp_config_bridge.default_hermes_root", lambda: hermes_home)
    monkeypatch.setattr(module, "_plugin_root", lambda: tmp_path / "plugin")
    monkeypatch.setattr(module, "_seed_pm_skill", lambda _dir: None)

    profile_dir = module.ensure_livingcolor_pm_profile()
    config = yaml.safe_load((profile_dir / "config.yaml").read_text(encoding="utf-8"))
    assert config["mcp_servers"]["Atlassian"]["command"] == "uvx"
