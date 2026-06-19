"""Agent surfaces: /delivery slash command and livingcolor model tools."""
import json

from delivery_runtime.persistence.db import connect, init_db, json_dumps, next_public_id, utc_now_iso
from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping


class FakeCtx:
    def __init__(self):
        self.commands = {}
        self.tools = {}

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands[name] = handler

    def register_tool(self, name, toolset, schema, handler, **kwargs):
        self.tools[name] = handler


def _registered(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from agent_surfaces import register_surfaces

    ctx = FakeCtx()
    register_surfaces(ctx)
    return ctx


def test_registers_delivery_command_and_tools(monkeypatch, tmp_path):
    ctx = _registered(monkeypatch, tmp_path)
    assert "delivery" in ctx.commands
    for tool in (
        "delivery_overview",
        "delivery_scan_readiness",
        "delivery_promote",
        "delivery_gate_decision",
        "delivery_work_order_status",
        "livingcolor_get_delivery_context",
        "livingcolor_update_ticket_estimation",
        "livingcolor_update_sprint_selection",
        "livingcolor_promote_ticket",
        "livingcolor_run_daily_analysis",
    ):
        assert tool in ctx.tools


def test_delivery_status_returns_text(monkeypatch, tmp_path):
    ctx = _registered(monkeypatch, tmp_path)
    out = ctx.commands["delivery"]("status")
    assert isinstance(out, str) and out


def test_overview_tool_returns_json(monkeypatch, tmp_path):
    ctx = _registered(monkeypatch, tmp_path)
    payload = json.loads(ctx.tools["delivery_overview"]({}))
    assert "workOrders" in payload or "readiness" in payload or payload


def test_promote_tool_supports_legacy_direct_route_call(monkeypatch, tmp_path):
    ctx = _registered(monkeypatch, tmp_path)
    install_phase25_project_mapping()
    init_db()
    from delivery_runtime.api import routes

    tick_calls: list[str] = []

    def fake_tick(services, work_order_id: str) -> None:
        tick_calls.append(work_order_id)

    monkeypatch.setattr(routes, "_run_promote_orchestrator_tick", fake_tick)
    with connect() as conn:
        record_id = next_public_id(conn, "RD")
        now = utc_now_iso()
        snapshot = {
            "key": "AAC-LEGACY",
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
            ) VALUES (?, ?, 'AAC', ?, 82, 'ready', 'Ready', '[]', '[]', 0.82, ?, ?, ?, ?)
            """,
            (
                record_id,
                snapshot["key"],
                snapshot["summary"],
                json_dumps(snapshot),
                now,
                now,
                now,
            ),
        )

    payload = json.loads(ctx.tools["delivery_promote"]({"record_id": record_id}))

    assert payload["readiness"]["readinessStatus"] == "promoted"
    assert payload["workOrder"]["jiraKey"] == "AAC-LEGACY"
    assert tick_calls == [payload["workOrder"]["id"]]
