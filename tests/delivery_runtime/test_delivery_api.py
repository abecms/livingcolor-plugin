"""Tests for Delivery Runtime HTTP API."""

import pytest

from delivery_runtime.persistence.db import connect, init_db, json_dumps, next_public_id, utc_now_iso
from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping


def _client():
    from delivery_http_client import delivery_api_client

    return delivery_api_client()


def _seed_ready_record(jira_key: str = "AAC-9") -> str:
    init_db()
    with connect() as conn:
        record_id = next_public_id(conn, "RD")
        now = utc_now_iso()
        snapshot = {
            "key": jira_key,
            "summary": "OAuth callback",
            "description": "Acceptance criteria: store token after OAuth completes.",
            "status": "To Do",
            "issueType": "Story",
            "projectKey": "AAC",
        }
        conn.execute(
            """
            INSERT INTO readiness_records (
                id, jira_key, project_key, title, readiness_score, readiness_status,
                analysis_summary, blockers_json, recommended_repos_json, confidence,
                jira_snapshot_json, analyzed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 82, 'ready', 'Ready', '[]', ?, 0.82, ?, ?, ?, ?)
            """,
            (
                record_id,
                jira_key,
                "AAC",
                snapshot["summary"],
                json_dumps(["gitlab.com/org/app"]),
                json_dumps(snapshot),
                now,
                now,
                now,
            ),
        )
    return record_id


class TestDeliveryApi:
    @pytest.fixture(autouse=True)
    def _setup(self, _isolate_hermes_home):
        install_phase25_project_mapping()
        self.client = _client()

    def test_overview_returns_empty_collections(self):
        response = self.client.get("/api/delivery/overview")
        assert response.status_code == 200
        payload = response.json()
        assert payload["readiness"]["items"] == []
        assert payload["workOrders"]["items"] == []
        assert payload["recentEvents"]["items"] == []

    def test_readiness_list_empty(self):
        response = self.client.get("/api/delivery/readiness")
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_work_orders_list_empty(self):
        response = self.client.get("/api/delivery/work-orders")
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_events_list_empty(self):
        response = self.client.get("/api/delivery/events")
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_unknown_work_order_returns_404(self):
        response = self.client.get("/api/delivery/work-orders/WO-404")
        assert response.status_code == 404

    def test_resume_unknown_work_order_returns_404(self):
        response = self.client.post("/api/delivery/work-orders/WO-404/resume")
        assert response.status_code == 404

    def test_resume_work_order_schedules_orchestrator(self, monkeypatch):
        record_id = _seed_ready_record("AAC-11")
        promote = self.client.post(f"/api/delivery/readiness/{record_id}/promote")
        work_order_id = promote.json()["workOrder"]["id"]
        scheduled: list[str] = []

        def _fake_schedule(orchestrator, wo_id):
            scheduled.append(wo_id)

        monkeypatch.setattr(
            "delivery_runtime.orchestration.background.schedule_orchestrator_tick",
            _fake_schedule,
        )

        response = self.client.post(f"/api/delivery/work-orders/{work_order_id}/resume")
        assert response.status_code == 200
        assert response.json() == {"workOrderId": work_order_id, "status": "scheduled"}
        assert scheduled == [work_order_id]

    def test_promote_ready_record(self):
        record_id = _seed_ready_record()
        response = self.client.post(f"/api/delivery/readiness/{record_id}/promote")
        assert response.status_code == 200
        payload = response.json()
        assert payload["workOrder"]["id"].startswith("WO-")
        assert payload["workOrder"]["jiraKey"] == "AAC-9"
        assert payload["readiness"]["readinessStatus"] == "promoted"
        assert payload["workOrder"]["status"] == "intake"

        promoted = self.client.get(f"/api/delivery/work-orders/{payload['workOrder']['id']}").json()
        assert promoted["status"] == "awaiting_gate"
        assert promoted["currentStage"] == "analysis_review"
        assert promoted["gates"][0]["gateType"] == "analysis_plan"

        work_orders = self.client.get("/api/delivery/work-orders").json()["items"]
        assert len(work_orders) == 1

    def test_scan_requires_project_key(self):
        response = self.client.post("/api/delivery/readiness/scan", json={"projectKey": ""})
        assert response.status_code == 400

    def test_gate_approve_and_reject_via_api(self):
        record_id = _seed_ready_record("AAC-10")
        promote = self.client.post(f"/api/delivery/readiness/{record_id}/promote")
        work_order_id = promote.json()["workOrder"]["id"]
        promoted = self.client.get(f"/api/delivery/work-orders/{work_order_id}").json()
        gate_id = promoted["gates"][0]["id"]

        reject = self.client.post(
            f"/api/delivery/gates/{gate_id}/reject",
            json={"feedback": "Clarify rollback strategy"},
        )
        assert reject.status_code == 200
        reject_payload = reject.json()
        assert reject_payload["gate"]["status"] == "rejected"

        work_order = self.client.get(f"/api/delivery/work-orders/{work_order_id}").json()
        pending_gate = next(gate for gate in work_order["gates"] if gate["status"] == "pending")
        approve = self.client.post(f"/api/delivery/gates/{pending_gate['id']}/approve")
        assert approve.status_code == 200
        assert approve.json()["gate"]["status"] == "approved"
        assert approve.json()["workOrderId"] == work_order["id"]

    def test_local_projects_list_and_create(self, tmp_path, monkeypatch):
        from delivery_runtime.automation import config as automation_config
        from delivery_runtime.persistence import paths as persistence_paths
        import lc_constants

        home = tmp_path / "livingcolor"
        monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: home)
        monkeypatch.setattr(persistence_paths, "get_livingcolor_home", lambda: home)
        monkeypatch.setattr(lc_constants, "get_livingcolor_home", lambda: home)

        config_dir = home / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "delivery.yaml").write_text(
            "project:\n  key: BN\n  name: Bibliothèque Numérique\n",
            encoding="utf-8",
        )

        initial = self.client.get("/api/delivery/projects")
        assert initial.status_code == 200
        assert initial.json()["projects"][0]["jiraProjectKey"] == "BN"
        initial_keys = {row["jiraProjectKey"] for row in initial.json()["projects"]}

        created = self.client.post(
            "/api/delivery/projects",
            json={"jiraProjectKey": "TV5", "projectName": "TV5 Monde"},
        )
        assert created.status_code == 200
        assert created.json()["jiraProjectKey"] == "TV5"

        listed = self.client.get("/api/delivery/projects")
        keys = {row["jiraProjectKey"] for row in listed.json()["projects"]}
        assert keys == initial_keys | {"TV5"}

    def test_project_config_get_and_put(self, tmp_path, monkeypatch):
        from delivery_runtime.automation import config as automation_config

        home = tmp_path / "livingcolor"
        monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: home)

        get_response = self.client.get("/api/delivery/project-config")
        assert get_response.status_code == 200
        payload = get_response.json()
        assert payload["projectKey"] == "BN"
        assert payload["sprintDurationDays"] == 14
        assert payload["sprintCapacityDays"] == 15.0
        assert payload["communicationLanguage"] == "fr"
        assert payload["ticketScope"]["statusGroups"] == ["todo"]

        put_response = self.client.put(
            "/api/delivery/project-config",
            json={
                "projectKey": "BN",
                "sprintDurationDays": 21,
                "sprintCapacityDays": 18.5,
                "communicationLanguage": "en",
                "ticketScope": {
                    "statusGroups": ["todo", "in_progress"],
                    "assignees": ["Ada Lovelace"],
                    "includeUnassigned": False,
                    "matchMode": "any",
                },
            },
        )
        assert put_response.status_code == 200
        updated = put_response.json()
        assert updated["sprintDurationDays"] == 21
        assert updated["sprintCapacityDays"] == 18.5
        assert updated["communicationLanguage"] == "en"
        assert updated["ticketScope"]["assignees"] == ["Ada Lovelace"]
        assert updated["ticketScope"]["matchMode"] == "any"

        reload = self.client.get("/api/delivery/project-config")
        assert reload.json()["sprintDurationDays"] == 21
        assert reload.json()["sprintCapacityDays"] == 18.5
        assert reload.json()["communicationLanguage"] == "en"

    def test_project_config_ticket_scope_is_scoped_by_request_project_key(self, tmp_path, monkeypatch):
        from delivery_runtime.automation import config as automation_config
        from delivery_runtime.readiness.project_mapping import load_project_mapping

        home = tmp_path / "livingcolor"
        monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: home)

        put_response = self.client.put(
            "/api/delivery/project-config",
            headers={"X-LC-Project-Key": "TV5"},
            json={
                "sprintDurationDays": 14,
                "sprintCapacityDays": 15,
                "communicationLanguage": "fr",
                "ticketScope": {
                    "statusGroups": ["todo"],
                    "assignees": ["Tamsi Besson", "Grégory Besson"],
                    "includeUnassigned": False,
                    "matchMode": "all",
                },
            },
        )
        assert put_response.status_code == 200
        assert put_response.json()["projectKey"] == "TV5"
        assert put_response.json()["ticketScope"]["assignees"] == ["Tamsi Besson", "Grégory Besson"]

        get_response = self.client.get("/api/delivery/project-config", headers={"X-LC-Project-Key": "TV5"})
        assert get_response.status_code == 200
        assert get_response.json()["ticketScope"]["assignees"] == ["Tamsi Besson", "Grégory Besson"]

        mapping = load_project_mapping()
        assert mapping["TV5"]["ticket_scope"]["assignees"] == ["Tamsi Besson", "Grégory Besson"]

    def test_project_config_update_recomputes_selected_sprint(self):
        from delivery_runtime.persistence.db import connect, init_db, json_dumps, next_public_id, utc_now_iso
        from delivery_runtime.pm_inbox import store as pm_store

        init_db()

        with connect() as conn:
            record_id = next_public_id(conn, "RD")
            now = utc_now_iso()
            conn.execute(
                """
                INSERT INTO readiness_records (
                    id, jira_key, project_key, title, readiness_score, readiness_status,
                    analysis_summary, blockers_json, recommended_repos_json, confidence,
                    jira_snapshot_json, analyzed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 90, 'ready', 'Ready', '[]', '[]', 0.9, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    "BN-1",
                    "BN",
                    "Small ticket",
                    json_dumps(
                        {
                            "key": "BN-1",
                            "summary": "Small",
                            "priority": "High",
                            "status": "To Do",
                            "statusCategory": "To Do",
                        }
                    ),
                    now,
                    now,
                    now,
                ),
            )
            pm_store.insert_estimation(
                conn,
                readiness_id=record_id,
                jira_key="BN-1",
                complexity="Small",
                estimated_days=1.0,
                confidence=0.9,
                run_id="RUN-1",
            )

            record_id_2 = next_public_id(conn, "RD")
            conn.execute(
                """
                INSERT INTO readiness_records (
                    id, jira_key, project_key, title, readiness_score, readiness_status,
                    analysis_summary, blockers_json, recommended_repos_json, confidence,
                    jira_snapshot_json, analyzed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 90, 'ready', 'Ready', '[]', '[]', 0.9, ?, ?, ?, ?)
                """,
                (
                    record_id_2,
                    "BN-2",
                    "BN",
                    "Large ticket",
                    json_dumps(
                        {
                            "key": "BN-2",
                            "summary": "Large",
                            "priority": "High",
                            "status": "To Do",
                            "statusCategory": "To Do",
                        }
                    ),
                    now,
                    now,
                    now,
                ),
            )
            pm_store.insert_estimation(
                conn,
                readiness_id=record_id_2,
                jira_key="BN-2",
                complexity="Large",
                estimated_days=3.0,
                confidence=0.8,
                run_id="RUN-1",
            )

        self.client.put(
            "/api/delivery/project-config",
            json={"sprintDurationDays": 14, "sprintCapacityDays": 2},
        )
        inbox = self.client.get("/api/delivery/pm-inbox?project=BN").json()
        selected = inbox["selectedSprint"]
        assert selected["capacityDays"] == 2
        assert len(selected["tickets"]) == 1
        assert selected["tickets"][0]["jiraKey"] == "BN-1"


class TestVcsReposApi:
    def test_list_project_vcs_repos_uses_github_discovery(self, monkeypatch):
        from delivery_runtime.api.routes import list_project_vcs_repos

        discovery = type(
            "Discovery",
            (),
            {
                "repos": [{"path": "github.com/org/app", "githubId": 1}],
                "default_repo": "github.com/org/app",
                "warnings": [],
            },
        )()

        monkeypatch.setattr(
            "delivery_runtime.readiness.project_settings.load_project_vcs_provider",
            lambda _key: "github",
        )
        monkeypatch.setattr(
            "delivery_runtime.readiness.project_settings.resolve_project_mcp_server",
            lambda _key, _provider: {"env": {"GITHUB_TOKEN": "ghp_test"}},
        )
        monkeypatch.setattr(
            "delivery_runtime.readiness.project_settings.load_project_default_repo",
            lambda _key: None,
        )
        monkeypatch.setattr(
            "lc_server.integrations.vcs.github.discover_github_repos_for_project",
            lambda _key, _cfg: discovery,
        )

        response = list_project_vcs_repos("APP")

        assert response.provider == "github"
        assert response.items[0].githubId == 1
        assert response.items[0].path == "github.com/org/app"
        assert response.defaultRepo == "github.com/org/app"

    def test_list_project_vcs_repos_github_mcp_not_configured(self, monkeypatch):
        from fastapi import HTTPException

        from delivery_runtime.api.routes import list_project_vcs_repos

        monkeypatch.setattr(
            "delivery_runtime.readiness.project_settings.load_project_vcs_provider",
            lambda _key: "github",
        )
        monkeypatch.setattr(
            "delivery_runtime.readiness.project_settings.resolve_project_mcp_server",
            lambda _key, _provider: None,
        )

        with pytest.raises(HTTPException) as exc_info:
            list_project_vcs_repos("APP")

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == {"error": "github_mcp_not_configured"}
