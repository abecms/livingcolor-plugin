"""Per-project delivery settings isolation."""

from delivery_runtime.automation.config import load_delivery_automation_config, save_delivery_project_config
from delivery_runtime.readiness.project_mapping import load_project_mapping
from delivery_runtime.readiness.project_settings import (
    load_project_delivery_settings,
    resolve_project_mcp_server,
)


def test_sprint_settings_are_isolated_per_project(tmp_path, monkeypatch):
    import lc_constants
    from delivery_runtime.automation import config as automation_config

    home = tmp_path / "livingcolor"
    monkeypatch.setattr(lc_constants, "get_livingcolor_home", lambda: home)
    monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: home)

    mapping_path = home / "project_mapping.yaml"
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.write_text(
        "BN:\n  name: Bibliothèque Numérique\nTV5:\n  name: TV5+\n",
        encoding="utf-8",
    )

    save_delivery_project_config(
        duration_days=21,
        capacity_days=18,
        communication_language="en",
        project_key="BN",
    )
    save_delivery_project_config(
        duration_days=10,
        capacity_days=12,
        communication_language="fr",
        project_key="TV5",
    )

    bn = load_delivery_automation_config(project_key="BN")
    tv5 = load_delivery_automation_config(project_key="TV5")

    assert bn.sprint.duration_days == 21
    assert bn.sprint.capacity_days == 18
    assert bn.communication_language == "en"
    assert tv5.sprint.duration_days == 10
    assert tv5.sprint.capacity_days == 12
    assert tv5.communication_language == "fr"

    mapping = load_project_mapping()
    assert mapping["BN"]["sprint"]["duration_days"] == 21
    assert mapping["TV5"]["sprint"]["duration_days"] == 10

    assert load_project_delivery_settings("BN").sprint_duration_days == 21
    assert load_project_delivery_settings("TV5").sprint_duration_days == 10


def test_resolve_project_mcp_server_falls_back_to_global_config(tmp_path, monkeypatch):
    import lc_constants
    from delivery_runtime.automation import config as automation_config

    home = tmp_path / "livingcolor"
    monkeypatch.setattr(lc_constants, "get_livingcolor_home", lambda: home)
    monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: home)

    mapping_path = home / "project_mapping.yaml"
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.write_text("TVP:\n  name: TV5+\n", encoding="utf-8")

    global_gitlab = {
        "command": "npx",
        "env": {
            "GITLAB_API_URL": "https://gitlab.tv5monde.com/api/v4",
            "GITLAB_PERSONAL_ACCESS_TOKEN": "secret-token",
        },
    }
    monkeypatch.setattr(
        "hermes_cli.mcp_config._get_mcp_servers",
        lambda: {"gitlab": global_gitlab},
    )

    resolved = resolve_project_mcp_server("TVP", "gitlab")
    assert resolved["env"]["GITLAB_API_URL"] == "https://gitlab.tv5monde.com/api/v4"


def test_persist_project_default_repo_updates_all_agent_manifests_and_automation_state(tmp_path, monkeypatch):
    import yaml
    import lc_constants
    from delivery_runtime.agents.paths import get_agent_manifest_path, get_automation_state_path
    from delivery_runtime.automation import config as automation_config
    from delivery_runtime.readiness.project_settings import persist_project_default_repo

    home = tmp_path / "livingcolor"
    monkeypatch.setattr(lc_constants, "get_livingcolor_home", lambda: home)
    monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: home)

    mapping_path = home / "project_mapping.yaml"
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.write_text("TVP:\n  name: TV5+\n", encoding="utf-8")

    stale_repo = "tv5monde/bibliotheque-numerique-v2"
    target_repo = "tv5monde/tv5mondeplus-front"

    for role in ("orchestrator", "analyst", "developer"):
        path = get_agent_manifest_path("TVP", role)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(
                {
                    "kind": "AgentManifest",
                    "role": role,
                    "context": {"defaultRepo": stale_repo, "projectKey": "TVP"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    get_automation_state_path("TVP").write_text(
        yaml.safe_dump(
            {
                "projectKey": "TVP",
                "status": "ready",
                "templateVersion": "1.0.0",
                "defaultRepo": stale_repo,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    persist_project_default_repo("TVP", target_repo)

    for role in ("orchestrator", "analyst", "developer"):
        manifest = yaml.safe_load(get_agent_manifest_path("TVP", role).read_text(encoding="utf-8"))
        assert manifest["context"]["defaultRepo"] == target_repo

    automation = yaml.safe_load(get_automation_state_path("TVP").read_text(encoding="utf-8"))
    assert automation["defaultRepo"] == target_repo


def test_project_vcs_provider_defaults_to_gitlab(livingcolor_home):
    from delivery_runtime.readiness.project_settings import load_project_vcs_provider

    assert load_project_vcs_provider("BN") == "gitlab"


def test_persist_project_vcs_provider_writes_mapping(livingcolor_home):
    from delivery_runtime.readiness.project_mapping import load_project_mapping
    from delivery_runtime.readiness.project_settings import (
        load_project_vcs_provider,
        persist_project_vcs_provider,
    )

    assert persist_project_vcs_provider("BN", "github") == "github"
    assert load_project_vcs_provider("BN") == "github"
    assert load_project_mapping()["BN"]["vcs"] == "github"


def test_project_config_update_rejects_unsupported_vcs_provider(monkeypatch):
    from fastapi import HTTPException

    from delivery_runtime.api.routes import update_project_config
    from delivery_runtime.api.schemas import ProjectConfigUpdateRequest

    monkeypatch.setattr(
        "delivery_runtime.api.routes._activate_local_project_from_request",
        lambda _request: "BN",
    )
    monkeypatch.setattr(
        "delivery_runtime.automation.config.save_delivery_project_config",
        lambda **_kwargs: None,
    )

    request = ProjectConfigUpdateRequest(
        sprintDurationDays=14,
        sprintCapacityDays=15,
        communicationLanguage="fr",
        vcs="bitbucket",
    )

    try:
        update_project_config(request, None)  # type: ignore[arg-type]
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Unsupported VCS provider" in str(exc.detail)
    else:
        raise AssertionError("Expected unsupported VCS provider to return HTTP 400")
