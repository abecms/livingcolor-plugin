from __future__ import annotations

import hashlib
import time
from unittest.mock import patch

import pytest
import yaml

VARIABLES = {
    "project_key": "BN",
    "project_name": "Bibliothèque Numérique",
    "language": "fr",
    "default_repo": "group/bn-frontend",
}


def test_render_developer_template_produces_valid_manifest():
    from delivery_runtime.agents.schema import parse_agent_manifest
    from lc_server.provisioning.template_renderer import render_role_template

    rendered = render_role_template("developer", variables=VARIABLES)
    manifest = parse_agent_manifest(rendered)
    assert manifest.role == "developer"
    assert manifest.context["projectKey"] == "BN"
    assert manifest.template_version == "1.8.0"
    assert manifest.template_checksum.startswith("sha256:")
    assert manifest.runtime.type == "hermes"
    assert manifest.runtime.max_iterations == 60
    assert manifest.runtime.toolsets == ("file", "terminal", "skills")
    assert manifest.runtime.model == "lc-developer"
    assert manifest.runtime.provider == "moa"
    assert "LivingColor Developer Agent" in manifest.prompt.system
    assert len(manifest.prompt.rules) >= 1
    skill_paths = {skill.path for skill in manifest.skills}
    assert "skills/delivery/agent-delivery-standards/SKILL.md" in skill_paths
    assert "skills/delivery/developer-workspace/SKILL.md" in skill_paths
    assert "skills/delivery/patch-quality/SKILL.md" in skill_paths
    assert "skills/delivery/thermo-nuclear-code-quality-review/SKILL.md" in skill_paths
    assert "skills/delivery/fix-merge-conflicts/SKILL.md" in skill_paths


def test_render_orchestrator_template_runtime_none():
    from delivery_runtime.agents.schema import parse_agent_manifest
    from lc_server.provisioning.template_renderer import render_role_template

    rendered = render_role_template("orchestrator", variables=VARIABLES)
    manifest = parse_agent_manifest(rendered)
    assert manifest.role == "orchestrator"
    assert manifest.runtime.type == "none"
    assert manifest.template_version == "1.8.0"
    assert manifest.template_checksum.startswith("sha256:")
    assert any(skill.path == "skills/delivery/agent-delivery-standards/SKILL.md" for skill in manifest.skills)


def test_render_analyst_template_runtime_hermes():
    from delivery_runtime.agents.schema import parse_agent_manifest
    from lc_server.provisioning.template_renderer import render_role_template

    rendered = render_role_template("analyst", variables=VARIABLES)
    manifest = parse_agent_manifest(rendered)
    assert manifest.role == "analyst"
    assert manifest.runtime.type == "hermes"
    assert manifest.runtime.max_iterations == 15
    assert manifest.runtime.toolsets == ()
    assert manifest.template_version == "1.8.0"
    assert manifest.template_checksum.startswith("sha256:")
    assert "LivingColor Analyst Agent" in manifest.prompt.system
    assert "readinessScore" in manifest.prompt.system
    assert any(skill.path == "skills/delivery/analyst-readiness/SKILL.md" for skill in manifest.skills)
    assert manifest.runtime.model == "lc-analyst"
    assert manifest.runtime.provider == "moa"
    from lc_server.provisioning.template_renderer import render_role_template

    rendered = render_role_template("developer", variables=VARIABLES)
    lines = rendered.splitlines()
    checksum_line = next(line for line in lines if line.startswith("templateChecksum:"))
    stored_checksum = checksum_line.split(":", 1)[1].strip().strip('"')
    content_for_hash = rendered.replace(checksum_line, 'templateChecksum: ""')
    expected = "sha256:" + hashlib.sha256(content_for_hash.encode("utf-8")).hexdigest()
    assert stored_checksum == expected


def test_templates_use_moa_provider():
    from lc_server.provisioning.template_renderer import render_role_template

    for role, model in (
        ("analyst", "lc-analyst"),
        ("planner", "lc-planner"),
        ("developer", "lc-developer"),
    ):
        rendered = render_role_template(role, variables=VARIABLES)
        assert "provider: moa" in rendered
        assert f"model: {model}" in rendered


def test_render_rejects_unknown_role():
    from lc_server.provisioning.template_renderer import render_role_template

    with pytest.raises(ValueError, match="role"):
        render_role_template("unknown", variables=VARIABLES)


def test_discover_repos_prefers_project_key_match():
    from lc_server.provisioning.gitlab_discovery import discover_gitlab_repos

    projects = [
        {
            "id": 1,
            "path_with_namespace": "group/bn-frontend",
            "name": "BN Frontend",
            "last_activity_at": "2026-06-10T00:00:00Z",
        },
        {
            "id": 2,
            "path_with_namespace": "group/other-app",
            "name": "Other",
            "last_activity_at": "2026-06-11T00:00:00Z",
        },
    ]
    result = discover_gitlab_repos(project_key="BN", projects=projects)
    assert result.default_repo == "group/bn-frontend"
    assert len(result.repos) == 1
    assert result.repos[0]["gitlabId"] == 1
    assert result.repos[0]["path"] == "group/bn-frontend"
    assert result.warnings == []


def test_discover_repos_single_repo_defaults_without_key_match():
    from lc_server.provisioning.gitlab_discovery import discover_gitlab_repos

    projects = [
        {
            "id": 42,
            "path_with_namespace": "group/only-one",
            "name": "Only One",
            "last_activity_at": "2026-06-01T00:00:00Z",
        },
    ]
    result = discover_gitlab_repos(project_key="BN", projects=projects)
    assert result.default_repo == "group/only-one"
    assert len(result.repos) == 1
    assert result.repos[0]["gitlabId"] == 42
    assert result.warnings == []


def test_discover_repos_multiple_matches_picks_latest_activity():
    from lc_server.provisioning.gitlab_discovery import discover_gitlab_repos

    projects = [
        {
            "id": 1,
            "path_with_namespace": "group/bn-frontend",
            "name": "BN Frontend",
            "last_activity_at": "2026-06-10T00:00:00Z",
        },
        {
            "id": 2,
            "path_with_namespace": "group/bn-backend",
            "name": "BN Backend",
            "last_activity_at": "2026-06-11T00:00:00Z",
        },
        {
            "id": 3,
            "path_with_namespace": "group/other-app",
            "name": "Other",
            "last_activity_at": "2026-06-12T00:00:00Z",
        },
    ]
    result = discover_gitlab_repos(project_key="BN", projects=projects)
    assert result.default_repo == "group/bn-backend"
    assert len(result.repos) == 2
    repo_paths = {repo["path"] for repo in result.repos}
    assert repo_paths == {"group/bn-frontend", "group/bn-backend"}
    assert result.warnings == []


def test_discover_repos_no_match_lists_all_with_warning():
    from lc_server.provisioning.gitlab_discovery import discover_gitlab_repos

    projects = [
        {
            "id": 2,
            "path_with_namespace": "group/alpha-app",
            "name": "Alpha",
            "last_activity_at": "2026-06-11T00:00:00Z",
        },
        {
            "id": 1,
            "path_with_namespace": "group/zeta-app",
            "name": "Zeta",
            "last_activity_at": "2026-06-10T00:00:00Z",
        },
    ]
    result = discover_gitlab_repos(project_key="BN", projects=projects)
    assert result.default_repo == "group/alpha-app"
    assert len(result.repos) == 2
    assert result.repos[0]["path"] == "group/alpha-app"
    assert result.repos[1]["path"] == "group/zeta-app"
    assert len(result.warnings) == 1
    assert "BN" in result.warnings[0]


def test_discover_repos_uses_mapping_repo_paths_without_key_substring_match():
    from lc_server.provisioning.gitlab_discovery import GitLabDiscoveryHints, discover_gitlab_repos

    projects = [
        {
            "id": 84,
            "path_with_namespace": "tv5monde/bibliotheque-numerique-v2",
            "name": "Bibliotheque Numerique V2",
            "last_activity_at": "2026-06-11T00:00:00Z",
        },
        {
            "id": 20,
            "path_with_namespace": "tv5monde/tv5mondeplus-front",
            "name": "TV5MONDE+ Front",
            "last_activity_at": "2026-06-12T00:00:00Z",
        },
    ]
    hints = GitLabDiscoveryHints(
        default_repo="tv5monde/bibliotheque-numerique-v2",
        repo_paths=(
            "tv5monde/bibliotheque-numerique-v2",
            "tv5monde/bibliotheque-numerique-v2-static",
            "tv5monde/tv5mondeplus-front",
        ),
    )

    result = discover_gitlab_repos(project_key="BN", projects=projects, hints=hints)

    assert result.default_repo == "tv5monde/bibliotheque-numerique-v2"
    assert {repo["path"] for repo in result.repos} == {
        "tv5monde/bibliotheque-numerique-v2",
        "tv5monde/tv5mondeplus-front",
    }
    assert result.warnings == []


def test_discover_repos_matches_bibliotheque_slug_when_default_repo_configured():
    from lc_server.provisioning.gitlab_discovery import GitLabDiscoveryHints, discover_gitlab_repos

    projects = [
        {
            "id": 84,
            "path_with_namespace": "tv5monde/bibliotheque-numerique-v2",
            "name": "Bibliotheque Numerique V2",
            "last_activity_at": "2026-06-11T00:00:00Z",
        },
        {
            "id": 20,
            "path_with_namespace": "tv5monde/tv5mondeplus-front",
            "name": "TV5MONDE+ Front",
            "last_activity_at": "2026-06-12T00:00:00Z",
        },
    ]
    hints = GitLabDiscoveryHints(default_repo="tv5monde/bibliotheque-numerique-v2")

    result = discover_gitlab_repos(project_key="BN", projects=projects, hints=hints)

    assert result.default_repo == "tv5monde/bibliotheque-numerique-v2"
    assert len(result.repos) == 1
    assert result.repos[0]["path"] == "tv5monde/bibliotheque-numerique-v2"
    assert result.warnings == []


def test_discover_gitlab_repos_for_project_uses_fetch():
    from unittest.mock import patch

    from lc_server.provisioning.gitlab_discovery import (
        discover_gitlab_repos_for_project,
    )

    mcp_config = {
        "env": {
            "GITLAB_PERSONAL_ACCESS_TOKEN": "test-token",
            "GITLAB_API_URL": "https://gitlab.com/api/v4",
        },
    }
    fetched_projects = [
        {
            "id": 9,
            "path_with_namespace": "group/bn-app",
            "name": "BN App",
            "last_activity_at": "2026-06-11T00:00:00Z",
        },
    ]

    with patch(
        "lc_server.provisioning.gitlab_discovery._fetch_gitlab_projects",
        return_value=fetched_projects,
    ) as mock_fetch:
        result = discover_gitlab_repos_for_project("BN", mcp_config)

    mock_fetch.assert_called_once_with(mcp_config)
    assert result.default_repo == "group/bn-app"
    assert result.repos[0]["gitlabId"] == 9


def test_prerequisites_ok_when_all_configured():
    from unittest.mock import patch

    from lc_server.provisioning.prerequisites import check_provisioning_prerequisites

    mcp_servers = {
        "jira": {"env": {"JIRA_URL": "https://jira.example.com", "JIRA_API_TOKEN": "token"}},
        "gitlab": {"env": {"GITLAB_PERSONAL_ACCESS_TOKEN": "gl-token"}},
    }

    with (
        patch(
            "lc_server.provisioning.prerequisites.resolve_project_mcp_server",
            lambda _project_key, server_name: mcp_servers.get(server_name),
        ),
        patch(
            "lc_server.provisioning.prerequisites.is_delivery_llm_available",
            return_value=True,
        ),
    ):
        missing = check_provisioning_prerequisites("BN")

    assert missing == []


def test_prerequisites_require_github_when_project_uses_github(monkeypatch):
    from lc_server.provisioning.prerequisites import check_provisioning_prerequisites

    servers = {
        "jira": {"env": {"JIRA_URL": "https://jira.example.com", "JIRA_API_TOKEN": "token"}},
        "github": {"env": {"GITHUB_TOKEN": "ghp_test"}},
    }

    monkeypatch.setattr(
        "lc_server.provisioning.prerequisites.load_project_vcs_provider",
        lambda project_key: "github",
    )
    monkeypatch.setattr(
        "lc_server.provisioning.prerequisites.resolve_project_mcp_server",
        lambda _project_key, server_name: servers.get(server_name),
    )
    monkeypatch.setattr(
        "lc_server.provisioning.prerequisites.is_delivery_llm_available",
        lambda: True,
    )

    assert check_provisioning_prerequisites("GH") == []


def test_prerequisites_do_not_require_gitlab_for_github(monkeypatch):
    from lc_server.provisioning.prerequisites import check_provisioning_prerequisites

    servers = {
        "jira": {"env": {"JIRA_URL": "https://jira.example.com", "JIRA_API_TOKEN": "token"}},
    }

    monkeypatch.setattr(
        "lc_server.provisioning.prerequisites.load_project_vcs_provider",
        lambda project_key: "github",
    )
    monkeypatch.setattr(
        "lc_server.provisioning.prerequisites.resolve_project_mcp_server",
        lambda _project_key, server_name: servers.get(server_name),
    )
    monkeypatch.setattr(
        "lc_server.provisioning.prerequisites.is_delivery_llm_available",
        lambda: True,
    )

    assert check_provisioning_prerequisites("GH") == ["github_mcp"]


def test_prerequisites_missing_jira():
    from unittest.mock import patch

    from lc_server.provisioning.prerequisites import check_provisioning_prerequisites

    mcp_servers = {
        "gitlab": {"env": {"GITLAB_PERSONAL_ACCESS_TOKEN": "gl-token"}},
    }

    with (
        patch(
            "lc_server.provisioning.prerequisites.resolve_project_mcp_server",
            lambda _project_key, server_name: mcp_servers.get(server_name),
        ),
        patch(
            "lc_server.provisioning.prerequisites.is_delivery_llm_available",
            return_value=True,
        ),
    ):
        missing = check_provisioning_prerequisites("BN")

    assert missing == ["jira_mcp"]


def test_require_raises_provision_error():
    from unittest.mock import patch

    import pytest

    from lc_server.provisioning.errors import ProvisionError
    from lc_server.provisioning.prerequisites import require_provisioning_prerequisites

    with patch(
        "lc_server.provisioning.prerequisites.check_provisioning_prerequisites",
        return_value=["jira_mcp", "llm_model"],
    ):
        with pytest.raises(ProvisionError) as exc_info:
            require_provisioning_prerequisites("BN")

    assert exc_info.value.missing == ["jira_mcp", "llm_model"]


def _mock_gitlab_discovery():
    from lc_server.provisioning.gitlab_discovery import GitLabDiscoveryResult

    return GitLabDiscoveryResult(
        repos=[
            {"path": "group/bn-frontend", "gitlabId": 1},
            {"path": "group/bn-backend", "gitlabId": 2},
        ],
        default_repo="group/bn-frontend",
    )


def test_provision_writes_manifests_and_mapping(livingcolor_home):
    from delivery_runtime.agents.paths import get_agent_manifest_path, get_automation_state_path
    from delivery_runtime.persistence.db import init_db
    from delivery_runtime.readiness.project_mapping import load_project_mapping
    from lc_server.provisioning.provisioner import ProjectAutomationProvisioner

    init_db()

    with (
        patch(
            "lc_server.provisioning.provisioner.require_provisioning_prerequisites",
        ),
        patch(
            "lc_server.provisioning.provisioner.discover_gitlab_repos_for_project",
            return_value=_mock_gitlab_discovery(),
        ),
    ):
        provisioner = ProjectAutomationProvisioner()
        result = provisioner.provision("BN")

    assert result.status == "ready"
    assert result.project_key == "BN"
    assert result.agents_provisioned == ["analyst", "developer", "orchestrator", "planner", "publisher", "reporter"]
    assert result.repos_discovered == 2
    assert result.default_repo == "group/bn-frontend"
    assert result.template_version == "1.8.0"
    assert result.warnings == []

    for role in ("orchestrator", "analyst", "planner", "developer", "publisher", "reporter"):
        assert get_agent_manifest_path("BN", role).is_file()

    automation = yaml.safe_load(get_automation_state_path("BN").read_text(encoding="utf-8"))
    assert automation["status"] == "ready"
    assert automation["templateVersion"] == "1.8.0"
    assert automation["reposDiscovered"] == 2
    assert automation["defaultRepo"] == "group/bn-frontend"
    assert automation["provisionedAt"]

    mapping = load_project_mapping()
    assert mapping["BN"]["default_repo"] == "group/bn-frontend"
    assert len(mapping["BN"]["repos"]) == 2


def test_provision_is_idempotent_without_force(livingcolor_home):
    from delivery_runtime.agents.paths import get_automation_state_path
    from delivery_runtime.persistence.db import init_db
    from lc_server.provisioning.provisioner import ProjectAutomationProvisioner

    init_db()

    with (
        patch(
            "lc_server.provisioning.provisioner.require_provisioning_prerequisites",
        ),
        patch(
            "lc_server.provisioning.provisioner.discover_gitlab_repos_for_project",
            return_value=_mock_gitlab_discovery(),
        ),
    ):
        provisioner = ProjectAutomationProvisioner()
        first = provisioner.provision("BN")
        first_mtime = get_automation_state_path("BN").stat().st_mtime
        first_provisioned_at = yaml.safe_load(
            get_automation_state_path("BN").read_text(encoding="utf-8")
        )["provisionedAt"]
        second = provisioner.provision("BN")

    assert second == first
    assert get_automation_state_path("BN").stat().st_mtime == first_mtime
    second_provisioned_at = yaml.safe_load(
        get_automation_state_path("BN").read_text(encoding="utf-8")
    )["provisionedAt"]
    assert second_provisioned_at == first_provisioned_at


def test_provision_force_rewrites_state(livingcolor_home):
    from delivery_runtime.agents.paths import get_agent_manifest_path, get_automation_state_path
    from delivery_runtime.persistence.db import init_db
    from lc_server.provisioning.provisioner import ProjectAutomationProvisioner

    init_db()
    timestamps = iter(["2026-06-11T09:00:00Z", "2026-06-11T10:00:00Z"])

    with (
        patch(
            "lc_server.provisioning.provisioner.require_provisioning_prerequisites",
        ),
        patch(
            "lc_server.provisioning.provisioner.discover_gitlab_repos_for_project",
            return_value=_mock_gitlab_discovery(),
        ),
        patch(
            "lc_server.provisioning.provisioner._utc_now_iso",
            side_effect=lambda: next(timestamps),
        ),
    ):
        provisioner = ProjectAutomationProvisioner()
        provisioner.provision("BN")
        first_provisioned_at = yaml.safe_load(
            get_automation_state_path("BN").read_text(encoding="utf-8")
        )["provisionedAt"]
        first_developer_mtime = get_agent_manifest_path("BN", "developer").stat().st_mtime
        time.sleep(0.02)
        second = provisioner.provision("BN", force=True)

    assert second.status == "ready"
    second_provisioned_at = yaml.safe_load(
        get_automation_state_path("BN").read_text(encoding="utf-8")
    )["provisionedAt"]
    assert second_provisioned_at != first_provisioned_at
    assert second_provisioned_at == "2026-06-11T10:00:00Z"
    assert first_provisioned_at == "2026-06-11T09:00:00Z"
    assert get_agent_manifest_path("BN", "developer").stat().st_mtime >= first_developer_mtime


def test_upgrade_rewrites_manifest_when_template_newer(livingcolor_home):
    from delivery_runtime.agents.paths import get_agent_manifest_path
    from delivery_runtime.agents.schema import parse_agent_manifest
    from delivery_runtime.persistence.db import init_db
    from lc_server.provisioning.provisioner import ProjectAutomationProvisioner
    from lc_server.provisioning.upgrade import upgrade_all_project_manifests

    init_db()

    with (
        patch(
            "lc_server.provisioning.provisioner.require_provisioning_prerequisites",
        ),
        patch(
            "lc_server.provisioning.provisioner.discover_gitlab_repos_for_project",
            return_value=_mock_gitlab_discovery(),
        ),
    ):
        ProjectAutomationProvisioner().provision("BN")

    developer_path = get_agent_manifest_path("BN", "developer")
    before = parse_agent_manifest(developer_path.read_text(encoding="utf-8"))
    assert before.template_version == "1.8.0"

    with patch(
        "lc_server.provisioning.template_renderer.get_template_version",
        return_value="1.9.0",
    ):
        upgraded = upgrade_all_project_manifests()

    assert "BN" in upgraded
    after = parse_agent_manifest(developer_path.read_text(encoding="utf-8"))
    assert after.template_version == "1.9.0"
    assert after.manually_edited is False


def test_upgrade_renders_newly_added_role_manifest(livingcolor_home):
    from delivery_runtime.agents.paths import get_agent_manifest_path
    from delivery_runtime.agents.schema import parse_agent_manifest
    from delivery_runtime.persistence.db import init_db
    from lc_server.provisioning.provisioner import ProjectAutomationProvisioner
    from lc_server.provisioning.upgrade import upgrade_all_project_manifests

    init_db()

    with (
        patch(
            "lc_server.provisioning.provisioner.require_provisioning_prerequisites",
        ),
        patch(
            "lc_server.provisioning.provisioner.discover_gitlab_repos_for_project",
            return_value=_mock_gitlab_discovery(),
        ),
    ):
        ProjectAutomationProvisioner().provision("BN")

    # Simulate a project provisioned before the planner role existed.
    planner_path = get_agent_manifest_path("BN", "planner")
    planner_path.unlink()

    with patch(
        "lc_server.provisioning.template_renderer.get_template_version",
        return_value="1.9.0",
    ):
        upgraded = upgrade_all_project_manifests()

    assert "BN" in upgraded
    assert planner_path.is_file()
    manifest = parse_agent_manifest(planner_path.read_text(encoding="utf-8"))
    assert manifest.role == "planner"
    assert manifest.template_version == "1.9.0"
    assert manifest.manually_edited is False
    assert manifest.context["projectKey"] == "BN"


def test_upgrade_skips_manually_edited_manifest(livingcolor_home):
    from delivery_runtime.agents.paths import get_agent_manifest_path
    from delivery_runtime.agents.schema import parse_agent_manifest
    from delivery_runtime.persistence.db import init_db
    from lc_server.provisioning.provisioner import ProjectAutomationProvisioner
    from lc_server.provisioning.upgrade import upgrade_all_project_manifests

    init_db()

    with (
        patch(
            "lc_server.provisioning.provisioner.require_provisioning_prerequisites",
        ),
        patch(
            "lc_server.provisioning.provisioner.discover_gitlab_repos_for_project",
            return_value=_mock_gitlab_discovery(),
        ),
    ):
        ProjectAutomationProvisioner().provision("BN")

    developer_path = get_agent_manifest_path("BN", "developer")
    original = developer_path.read_text(encoding="utf-8")
    edited = original.replace("manuallyEdited: false", "manuallyEdited: true", 1)
    developer_path.write_text(edited, encoding="utf-8")

    with patch(
        "lc_server.provisioning.template_renderer.get_template_version",
        return_value="1.9.0",
    ):
        upgraded = upgrade_all_project_manifests()

    assert "BN" in upgraded
    developer = parse_agent_manifest(developer_path.read_text(encoding="utf-8"))
    assert developer.manually_edited is True
    assert developer.template_version == "1.8.0"

    orchestrator = parse_agent_manifest(
        get_agent_manifest_path("BN", "orchestrator").read_text(encoding="utf-8")
    )
    assert orchestrator.template_version == "1.9.0"
    assert orchestrator.manually_edited is False
