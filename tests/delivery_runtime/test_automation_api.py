"""Tests for project automation setup API endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lc_server.provisioning.errors import ProvisionError
from lc_server.provisioning.provisioner import ProvisionResult


def _client():
    from delivery_http_client import delivery_api_client

    return delivery_api_client()


def _provision_result(*, warnings: list[str] | None = None) -> ProvisionResult:
    return ProvisionResult(
        status="ready",
        project_key="BN",
        agents_provisioned=["analyst", "developer", "orchestrator"],
        repos_discovered=2,
        default_repo="group/bn-frontend",
        template_version="1.0.0",
        warnings=warnings or [],
    )


class TestSetupAutomationApi:
    @pytest.fixture(autouse=True)
    def _setup(self, _isolate_hermes_home):
        self.client = _client()

    def test_setup_automation_returns_400_when_prerequisites_missing(self):
        with patch(
            "lc_server.provisioning.provisioner.ProjectAutomationProvisioner"
        ) as mock_cls:
            mock_cls.return_value.provision.side_effect = ProvisionError(
                ["jira_mcp", "gitlab_mcp"]
            )
            response = self.client.post("/api/delivery/projects/BN/setup-automation")

        assert response.status_code == 400
        assert response.json() == {
            "detail": {
                "error": "prerequisites_missing",
                "missing": ["jira_mcp", "gitlab_mcp"],
            }
        }
        mock_cls.return_value.provision.assert_called_once_with("BN", force=False)

    def test_setup_automation_returns_200(self):
        with patch(
            "lc_server.provisioning.provisioner.ProjectAutomationProvisioner"
        ) as mock_cls:
            mock_cls.return_value.provision.return_value = _provision_result(
                warnings=["GitLab discovery failed: timeout"]
            )
            response = self.client.post("/api/delivery/projects/bn/setup-automation")

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["projectKey"] == "BN"
        assert payload["agentsProvisioned"] == ["analyst", "developer", "orchestrator"]
        assert payload["reposDiscovered"] == 2
        assert payload["defaultRepo"] == "group/bn-frontend"
        assert payload["templateVersion"] == "1.0.0"
        assert payload["warnings"] == ["GitLab discovery failed: timeout"]
        mock_cls.return_value.provision.assert_called_once_with("BN", force=False)

    def test_setup_automation_idempotent_second_call(self):
        with patch(
            "lc_server.provisioning.provisioner.ProjectAutomationProvisioner"
        ) as mock_cls:
            mock_cls.return_value.provision.return_value = _provision_result()
            first = self.client.post("/api/delivery/projects/BN/setup-automation")
            second = self.client.post("/api/delivery/projects/BN/setup-automation")

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == second.json()
        assert mock_cls.return_value.provision.call_count == 2
        mock_cls.return_value.provision.assert_called_with("BN", force=False)

    def test_setup_automation_passes_force_query_param(self):
        with patch(
            "lc_server.provisioning.provisioner.ProjectAutomationProvisioner"
        ) as mock_cls:
            mock_cls.return_value.provision.return_value = _provision_result()
            response = self.client.post("/api/delivery/projects/BN/setup-automation?force=true")

        assert response.status_code == 200
        mock_cls.return_value.provision.assert_called_once_with("BN", force=True)


class TestGetAutomationApi:
    @pytest.fixture(autouse=True)
    def _setup(self, _isolate_hermes_home):
        self.client = _client()

    def test_get_automation_returns_404_when_not_provisioned(self, livingcolor_home):
        response = self.client.get("/api/delivery/projects/BN/automation")
        assert response.status_code == 404
        assert response.json()["detail"] == "Automation not provisioned"

    def test_get_automation_returns_status_when_provisioned(self, livingcolor_home):
        from delivery_runtime.agents.paths import get_agent_manifest_path, get_automation_state_path
        from lc_server.provisioning.template_renderer import render_role_template

        project_key = "BN"
        variables = {
            "project_key": project_key,
            "project_name": "Bibliothèque Numérique",
            "language": "fr",
            "default_repo": "group/bn-frontend",
        }
        agents_dir = get_agent_manifest_path(project_key, "developer").parent
        agents_dir.mkdir(parents=True)
        for role in ("orchestrator", "analyst", "developer"):
            rendered = render_role_template(role, variables=variables)
            get_agent_manifest_path(project_key, role).write_text(rendered, encoding="utf-8")

        get_automation_state_path(project_key).write_text(
            "\n".join(
                [
                    "projectKey: BN",
                    "status: ready",
                    "templateVersion: '1.0.0'",
                    "provisionedAt: '2026-06-11T12:00:00Z'",
                    "reposDiscovered: 2",
                    "defaultRepo: group/bn-frontend",
                ]
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/delivery/projects/bn/automation")

        assert response.status_code == 200
        payload = response.json()
        assert payload["projectKey"] == "BN"
        assert payload["status"] == "ready"
        assert payload["templateVersion"] == "1.0.0"
        assert payload["provisionedAt"] == "2026-06-11T12:00:00Z"
        assert len(payload["agents"]) == 3
        roles = {agent["role"] for agent in payload["agents"]}
        assert roles == {"orchestrator", "analyst", "developer"}
        for agent in payload["agents"]:
            assert agent["templateVersion"] == "1.0.0"
            assert agent["runtimeType"] in {"hermes", "none"}


class TestGitlabReposApi:
    @pytest.fixture(autouse=True)
    def _setup(self, _isolate_hermes_home):
        self.client = _client()

    def test_gitlab_repos_uses_global_gitlab_config(self, livingcolor_home, monkeypatch):
        global_gitlab = {
            "command": "npx",
            "env": {
                "GITLAB_API_URL": "https://gitlab.example.com/api/v4",
                "GITLAB_PERSONAL_ACCESS_TOKEN": "token",
            },
        }
        monkeypatch.setattr(
            "hermes_cli.mcp_config._get_mcp_servers",
            lambda: {"gitlab": global_gitlab},
        )

        discovery = type(
            "Discovery",
            (),
            {
                "repos": [{"path": "tv5monde/tv5mondeplus-front", "gitlabId": 42}],
                "default_repo": "tv5monde/tv5mondeplus-front",
                "warnings": [],
            },
        )()

        with patch(
            "lc_server.provisioning.gitlab_discovery.discover_gitlab_repos_for_project",
            return_value=discovery,
        ) as mock_discover:
            response = self.client.get("/api/delivery/projects/TVP/gitlab-repos")

        assert response.status_code == 200
        payload = response.json()
        assert payload["items"] == [{"path": "tv5monde/tv5mondeplus-front", "gitlabId": 42}]
        assert payload["defaultRepo"] == "tv5monde/tv5mondeplus-front"
        mock_discover.assert_called_once()
        assert mock_discover.call_args.args[0] == "TVP"
        assert mock_discover.call_args.args[1]["env"]["GITLAB_API_URL"] == "https://gitlab.example.com/api/v4"


class TestProjectConfigApi:
    @pytest.fixture(autouse=True)
    def _setup(self, _isolate_hermes_home, livingcolor_home):
        self.client = _client()
        mapping_path = livingcolor_home / "project_mapping.yaml"
        mapping_path.write_text("TVP:\n  name: TV5+\n", encoding="utf-8")

    def test_update_project_config_persists_default_repo(self, livingcolor_home):
        import yaml
        from delivery_runtime.agents.paths import get_agent_manifest_path, get_automation_state_path

        stale_repo = "tv5monde/bibliotheque-numerique-v2"
        target_repo = "tv5monde/tv5mondeplus-front"

        for role in ("orchestrator", "analyst", "developer"):
            path = get_agent_manifest_path("TVP", role)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                yaml.safe_dump({"role": role, "context": {"defaultRepo": stale_repo}}, sort_keys=False),
                encoding="utf-8",
            )

        get_automation_state_path("TVP").write_text(
            yaml.safe_dump({"projectKey": "TVP", "defaultRepo": stale_repo}, sort_keys=False),
            encoding="utf-8",
        )

        response = self.client.put(
            "/api/delivery/project-config",
            headers={"x-lc-project-key": "TVP"},
            json={
                "sprintDurationDays": 14,
                "sprintCapacityDays": 15,
                "communicationLanguage": "fr",
                "defaultRepo": target_repo,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["defaultRepo"] == target_repo

        for role in ("orchestrator", "analyst", "developer"):
            manifest = yaml.safe_load(get_agent_manifest_path("TVP", role).read_text(encoding="utf-8"))
            assert manifest["context"]["defaultRepo"] == target_repo

        automation = yaml.safe_load(get_automation_state_path("TVP").read_text(encoding="utf-8"))
        assert automation["defaultRepo"] == target_repo

    def test_update_project_config_persists_integration_branch(self, livingcolor_home):
        import yaml

        response = self.client.put(
            "/api/delivery/project-config",
            headers={"x-lc-project-key": "TVP"},
            json={
                "sprintDurationDays": 14,
                "sprintCapacityDays": 15,
                "communicationLanguage": "fr",
                "integrationBranch": "develop",
            },
        )

        assert response.status_code == 200
        assert response.json()["integrationBranch"] == "develop"

        mapping = yaml.safe_load((livingcolor_home / "project_mapping.yaml").read_text(encoding="utf-8"))
        assert mapping["TVP"]["integration_branch"] == "develop"

    def test_update_project_config_does_not_rebuild_sprint_selection(self, livingcolor_home):
        from delivery_runtime.pm_inbox.sprint_mutations import persist_manual_sprint
        from delivery_runtime.pm_inbox.store import get_sprint_state

        persist_manual_sprint(
            project_key="TVP",
            payload={
                "sprintName": "LivingColor Sprint",
                "capacityDays": 15,
                "usedDays": 1,
                "durationDays": 14,
                "overflowRisk": False,
                "warnings": [],
                "tickets": [
                    {
                        "readinessId": "RD-TVP-9",
                        "jiraKey": "TVP-9",
                        "title": "Manual ticket",
                        "estimatedDays": 1,
                    }
                ],
            },
        )

        response = self.client.put(
            "/api/delivery/project-config",
            headers={"x-lc-project-key": "TVP"},
            json={
                "projectKey": "TVP",
                "sprintDurationDays": 21,
                "sprintCapacityDays": 18,
                "communicationLanguage": "fr",
            },
        )

        assert response.status_code == 200
        state = get_sprint_state(project_key="TVP")
        assert state is not None
        recommendation = state["recommendation"]
        assert recommendation["tickets"][0]["jiraKey"] == "TVP-9"
        assert state["memory"]["manualOverride"] is True

    def test_reset_sprint_clears_backlog_for_manual_reset(self, livingcolor_home):
        from delivery_runtime.pm_inbox.sprint_mutations import persist_manual_sprint
        from delivery_runtime.pm_inbox.store import get_sprint_state

        persist_manual_sprint(
            project_key="TVP",
            payload={
                "sprintName": "LivingColor Sprint",
                "capacityDays": 15,
                "usedDays": 2,
                "durationDays": 14,
                "overflowRisk": False,
                "warnings": [],
                "tickets": [
                    {
                        "readinessId": "RD-TVP-9",
                        "jiraKey": "TVP-9",
                        "title": "Manual ticket",
                        "estimatedDays": 2,
                    }
                ],
            },
        )

        response = self.client.post(
            "/api/delivery/sprint/reset",
            headers={"x-lc-project-key": "TVP"},
            json={"projectKey": "TVP"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["tickets"] == []
        state = get_sprint_state(project_key="TVP")
        assert state is not None
        assert state["memory"]["manualOverride"] is False


class TestSprintReportApi:
    @pytest.fixture(autouse=True)
    def _setup(self, _isolate_hermes_home, livingcolor_home):
        self.client = _client()

    def test_sprint_report_response_includes_billing_fields(self, monkeypatch, livingcolor_home):
        from delivery_runtime.pm_inbox.sprint_selection import persist_selected_sprint

        persist_selected_sprint(
            project_key="TVP",
            payload={
                "sprintName": "LivingColor Sprint",
                "capacityDays": 15,
                "usedDays": 1,
                "durationDays": 14,
                "overflowRisk": False,
                "warnings": [],
                "tickets": [],
            },
            memory_patch={
                "sprintNumber": 1,
                "sprintStartDate": "2026-06-17",
                "sprintEndDate": "2026-06-30",
            },
        )

        def fake_publish_sprint_report(*, project_key, force=False, actor="human"):
            return {
                "status": "sent",
                "dedupKey": "1:2026-06-30",
                "platform": "slack",
                "publishedAt": "2026-06-30T16:00:00+00:00",
                "messagePreview": "Sprint report",
                "billingStatus": "draft_created",
                "invoiceId": "in_123",
                "invoiceUrl": "https://invoice.stripe.com/in_123",
                "invoiceStatus": "draft",
                "invoiceTotalCents": 160000,
                "invoiceCurrency": "eur",
                "billingWarning": None,
            }

        monkeypatch.setattr(
            "delivery_runtime.pm_inbox.sprint_report.publish_sprint_report",
            fake_publish_sprint_report,
        )

        response = self.client.post("/api/delivery/sprint/report", headers={"x-lc-project-key": "TVP"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["billingStatus"] == "draft_created"
        assert payload["invoiceUrl"] == "https://invoice.stripe.com/in_123"
        assert payload["invoiceTotalCents"] == 160000


    def test_project_config_ignores_legacy_billing_payload(self, livingcolor_home, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")

        response = self.client.put(
            "/api/delivery/project-config",
            headers={"x-lc-project-key": "TVP"},
            json={
                "sprintDurationDays": 14,
                "sprintCapacityDays": 15,
                "communicationLanguage": "fr",
                "billing": {
                    "stripeCustomerId": "cus_123",
                    "dailyRateCents": 80000,
                },
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert "billing" not in payload

        settings = self.client.get("/api/delivery/plugin-settings")
        assert settings.status_code == 200
        assert settings.json()["billing"]["stripeCustomerId"] is None

        get_response = self.client.get(
            "/api/delivery/project-config",
            headers={"x-lc-project-key": "TVP"},
        )
        assert get_response.status_code == 200
        assert "billing" not in get_response.json()
