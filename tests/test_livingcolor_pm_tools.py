from __future__ import annotations

import json

from livingcolor_pm_tools import (
    _serialize_project_settings,
    resolve_active_livingcolor_project_key,
    tool_get_delivery_context,
)


def test_resolve_active_livingcolor_project_key_prefers_explicit(monkeypatch):
    monkeypatch.setenv("HERMES_TUI_LIVINGCOLOR_PROJECT_KEY", "BN")
    assert resolve_active_livingcolor_project_key("tvp") == "TVP"


def test_resolve_active_livingcolor_project_key_uses_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_TUI_LIVINGCOLOR_PROJECT_KEY", "bn")
    assert resolve_active_livingcolor_project_key() == "BN"


def test_get_delivery_context_tool_scopes_to_env_project(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_TUI_LIVINGCOLOR_PROJECT_KEY", "AAC")

    from delivery_runtime.persistence.db import init_db
    from lc_server.factory import build_delivery_services
    from delivery_runtime.api import deps

    init_db()
    deps.configure(build_delivery_services())

    payload = json.loads(tool_get_delivery_context({}, project_key="AAC"))
    assert payload["success"] is True
    assert payload["projectKey"] == "AAC"
    assert payload["projectSettings"]["projectKey"] == "AAC"


def test_serialize_project_settings_uses_per_project_mapping(tmp_path, monkeypatch):
    import lc_constants
    from delivery_runtime.automation import config as automation_config
    from delivery_runtime.automation.config import save_delivery_project_config

    home = tmp_path / "livingcolor"
    monkeypatch.setattr(lc_constants, "get_livingcolor_home", lambda: home)
    monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: home)

    mapping_path = home / "project_mapping.yaml"
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.write_text("TVP:\n  name: TV5+\n", encoding="utf-8")

    save_delivery_project_config(
        duration_days=7,
        capacity_days=2,
        communication_language="fr",
        start_weekday=3,
        project_key="TVP",
    )

    settings = _serialize_project_settings("TVP")
    assert settings["communicationLanguage"] == "fr"
    assert settings["sprint"]["durationDays"] == 7
    assert settings["sprint"]["capacityDays"] == 2
    assert settings["sprint"]["startWeekday"] == 3


def test_project_settings_visible_under_profile_scoped_hermes_home(tmp_path, monkeypatch):
    from pathlib import Path

    import lc_constants
    from delivery_runtime.automation.config import save_delivery_project_config
    from delivery_runtime.readiness.ticket_scope import parse_ticket_scope

    root = tmp_path / ".hermes"
    profile = root / "profiles" / "livingcolor-pm"
    profile.mkdir(parents=True)
    livingcolor_home = root / "livingcolor"
    livingcolor_home.mkdir(parents=True)

    mapping_path = livingcolor_home / "project_mapping.yaml"
    mapping_path.write_text("TVP:\n  name: TV5+\n", encoding="utf-8")

    monkeypatch.setenv("HERMES_HOME", str(profile))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lc_constants, "_default_hermes_root", lambda: root)

    save_delivery_project_config(
        duration_days=7,
        capacity_days=2,
        communication_language="fr",
        project_key="TVP",
    )

    settings = _serialize_project_settings("TVP")
    assert settings["ticketScope"]["assignees"] == []

    save_delivery_project_config(
        duration_days=7,
        capacity_days=2,
        communication_language="fr",
        project_key="TVP",
        ticket_scope=parse_ticket_scope(
            {
                "statusGroups": ["todo"],
                "assignees": ["Tamsi Besson", "Grégory Besson"],
                "includeUnassigned": False,
                "matchMode": "all",
            }
        ),
    )

    settings = _serialize_project_settings("TVP")
    assert settings["ticketScope"]["assignees"] == ["Tamsi Besson", "Grégory Besson"]
