"""Tests for Phase 4A Merge Request Draft infrastructure."""

from __future__ import annotations

import os

import pytest

from delivery_runtime.gates.constants import CODE_REVIEW_GATE_TYPE, GATE1_TYPE, MR_REVIEW_GATE_TYPE
from delivery_runtime.gates.service import GateService
from delivery_runtime.mr_drafts.generator import generate_mr_draft_content
from delivery_runtime.mr_drafts.service import MrDraftService
from delivery_runtime.mr_drafts.store import load_mr_draft
from delivery_runtime.persistence.db import connect, init_db, json_dumps, next_public_id, utc_now_iso
from delivery_runtime.shadow.guards import check_mcp_tool, get_shadow_audit_log, reset_shadow_audit_log
from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping
from delivery_runtime.events.store import EventStore
from delivery_runtime.orchestration.engine import OrchestrationEngine
from delivery_runtime.pm_inbox.queue_consumer import ExecutionQueueConsumer
from delivery_runtime.readiness.service import ReadinessService
from delivery_runtime.work_orders.service import WorkOrderService
from lc_server.agent_bridge.hermes_runtime import HermesRuntimeBridge


def _build_services():
    install_phase25_project_mapping()
    events = EventStore()
    bridge = HermesRuntimeBridge()
    mr_drafts = MrDraftService(events)
    gates = GateService(events, mr_drafts=mr_drafts)
    orchestrator = OrchestrationEngine(events, agent_bridge=bridge, gate_service=gates)
    gates.bind_orchestrator(orchestrator)
    work_orders = WorkOrderService(events)
    readiness = ReadinessService(events, work_orders=work_orders, orchestrator=orchestrator)
    return readiness, work_orders, gates, mr_drafts, events


def _insert_ready_record(conn, *, jira_key: str = "AAC-55") -> str:
    record_id = next_public_id(conn, "RD")
    now = utc_now_iso()
    snapshot = {
        "key": jira_key,
        "summary": "Fix OAuth callback thumbnail",
        "description": "Acceptance criteria: persist OAuth tokens after callback.",
        "status": "To Do",
        "issueType": "Story",
        "projectKey": "AAC",
        "priority": "High",
    }
    conn.execute(
        """
        INSERT INTO readiness_records (
            id, jira_key, project_key, title, readiness_score, readiness_status,
            analysis_summary, blockers_json, recommended_repos_json, confidence,
            jira_snapshot_json, analyzed_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 88, 'ready', ?, '[]', ?, 0.88, ?, ?, ?, ?)
        """,
        (
            record_id,
            jira_key,
            "AAC",
            snapshot["summary"],
            snapshot["summary"],
            json_dumps(["gitlab.com/org/app"]),
            json_dumps(snapshot),
            now,
            now,
            now,
        ),
    )
    return record_id


def test_generate_mr_draft_content_uses_patch_evidence_only():
    content = generate_mr_draft_content(
        jira_key="BN-516",
        work_order_title="Fix criteria input",
        jira_snapshot={"summary": "Fix criteria input", "description": "Acceptance criteria: update thumbnail"},
        approved_plan={
            "implementationPlan": "1. Edit component\n2. Add test",
            "likelyImpactedFiles": ["admin/src/components/CriteresAutomatiquesInput.tsx"],
            "risks": ["Regression on criteria validation"],
            "targetRepo": "gitlab.com/org/bibnum",
        },
        context_pack={"identified_repo": "gitlab.com/org/bibnum"},
        code_review_payload={
            "summary": "Updated criteria input handling.",
            "filesModified": ["admin/src/components/CriteresAutomatiquesInput.tsx"],
            "filesCreated": ["admin/tests/components/CriteresAutomatiquesInput.test.tsx"],
            "patchStats": {"linesChanged": 24},
            "scopeValidation": {"outcome": "PASS", "scopePrecision": 1.0, "scopeRecall": 1.0},
            "testRun": {"passed": True},
        },
    )

    assert content["title"].startswith("BN-516")
    assert "admin/src/components/CriteresAutomatiquesInput.tsx" in content["filesModified"]
    assert "Regression on criteria validation" in content["risks"]
    assert "### Context" in content["description"]
    assert content["qaChecklist"]["build"] == "PASS"
    assert content["qaChecklist"]["tests"] == "PASS"
    assert content["qaChecklist"]["scopeValidation"] == "PASS"


def test_code_review_approve_to_mr_draft_end_to_end(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        record_id = _insert_ready_record(conn)

    readiness, work_orders, gates, mr_drafts, events = _build_services()
    work_order = readiness.promote(record_id)
    gates.approve(work_order["gates"][0]["id"])
    updated = work_orders.get_work_order(work_order["id"])
    code_gate = next(g for g in updated["gates"] if g["gateType"] == CODE_REVIEW_GATE_TYPE)
    gates.approve(code_gate["id"])

    updated = work_orders.get_work_order(work_order["id"])
    mr_gate = next(g for g in updated["gates"] if g["gateType"] == MR_REVIEW_GATE_TYPE and g["status"] == "pending")
    draft = load_mr_draft(mr_gate["payload"]["draftId"])
    assert draft is not None
    assert draft.status == "awaiting_review"
    assert updated["currentStage"] == "mr_draft"

    approved = mr_drafts.approve_draft(draft.id)
    assert approved.status == "approved"
    updated = work_orders.get_work_order(work_order["id"])
    assert updated["currentStage"] == "awaiting_next_phase"
    assert updated["status"] == "running"

    event_types = [event["eventType"] for event in events.list_for_work_order(work_order["id"], limit=50)]
    assert "MR_DRAFT_CREATED" in event_types
    assert "MR_DRAFT_APPROVED" in event_types


def test_mr_draft_api_endpoints(_isolate_hermes_home):
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi/starlette not installed")

    from hermes_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN, app

    init_db()
    with connect() as conn:
        record_id = _insert_ready_record(conn, jira_key="AAC-56")

    readiness, work_orders, gates, mr_drafts, _events = _build_services()
    work_order = readiness.promote(record_id)
    gates.approve(work_order["gates"][0]["id"])
    updated = work_orders.get_work_order(work_order["id"])
    code_gate = next(g for g in updated["gates"] if g["gateType"] == CODE_REVIEW_GATE_TYPE)
    gates.approve(code_gate["id"])
    updated = work_orders.get_work_order(work_order["id"])
    mr_gate = next(g for g in updated["gates"] if g["gateType"] == MR_REVIEW_GATE_TYPE and g["status"] == "pending")
    draft_id = mr_gate["payload"]["draftId"]

    from delivery_runtime.api.deps import DeliveryServices, configure

    from delivery_runtime.pm_inbox.service import PmInboxService

    configure(
        DeliveryServices(
            readiness=readiness,
            work_orders=work_orders,
            events=EventStore(),
            gates=gates,
            orchestrator=OrchestrationEngine(EventStore(), agent_bridge=HermesRuntimeBridge(), gate_service=gates),
            agent_bridge=HermesRuntimeBridge(),
            mr_drafts=mr_drafts,
            pm_inbox=PmInboxService(),
            queue_consumer=ExecutionQueueConsumer(),
        )
    )

    client = TestClient(app)
    client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN

    get_resp = client.get(f"/api/delivery/mr-drafts/{draft_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == draft_id

    approve_resp = client.post(f"/api/delivery/mr-drafts/{draft_id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["draft"]["status"] == "approved"


@pytest.fixture(autouse=True)
def _shadow_env(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_SHADOW_MODE", "true")
    reset_shadow_audit_log()


def test_mr_draft_flow_blocks_gitlab_writes_in_shadow_mode():
    violation = check_mcp_tool("gitlab", "create_merge_request")
    assert violation is not None
    assert get_shadow_audit_log().to_dict()["violationCount"] >= 1

    os.environ["LIVINGCOLOR_SHADOW_MODE"] = "true"
    reset_shadow_audit_log()
    assert check_mcp_tool("gitlab", "create_branch") is not None
    assert get_shadow_audit_log().to_dict()["violationCount"] >= 1
