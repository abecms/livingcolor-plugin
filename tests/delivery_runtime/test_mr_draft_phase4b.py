"""Tests for Phase 4B explainable MR Draft delivery."""

from __future__ import annotations

import pytest

from delivery_runtime.explainability import build_decision_trace
from delivery_runtime.gates.constants import CODE_REVIEW_GATE_TYPE, MR_REVIEW_GATE_TYPE
from delivery_runtime.gates.service import GateService
from delivery_runtime.mr_drafts.generator import generate_mr_draft_content
from delivery_runtime.mr_drafts.service import MrDraftService
from delivery_runtime.mr_drafts.store import load_mr_draft
from delivery_runtime.persistence.db import connect, init_db, json_dumps, next_public_id, utc_now_iso
from delivery_runtime.shadow.guards import check_mcp_tool, get_shadow_audit_log, reset_shadow_audit_log
from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping
from delivery_runtime.events.store import EventStore
from delivery_runtime.orchestration.engine import OrchestrationEngine
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


def _insert_ready_record(conn, *, jira_key: str = "BN-516") -> str:
    record_id = next_public_id(conn, "RD")
    now = utc_now_iso()
    project_key = jira_key.split("-", 1)[0]
    summary = (
        "Fix OAuth callback thumbnail"
        if project_key == "AAC"
        else "Fix author thumbnail rendering"
    )
    description = (
        "Acceptance criteria: persist OAuth tokens after callback."
        if project_key == "AAC"
        else "Acceptance criteria: update author vignette display in criteria input."
    )
    snapshot = {
        "key": jira_key,
        "summary": summary,
        "description": description,
        "status": "To Do",
        "issueType": "Story",
        "projectKey": project_key,
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
            project_key,
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


def test_build_decision_trace_produces_file_reasoning():
    trace = build_decision_trace(
        jira_key="BN-516",
        jira_snapshot={
            "summary": "Fix author thumbnail rendering",
            "description": "Acceptance criteria: update author vignette display.",
        },
        approved_plan={
            "confidenceLevel": 0.87,
            "likelyImpactedFiles": ["admin/src/components/CriteresAutomatiquesInput.tsx"],
            "ticketUnderstanding": "BN-516 targets author thumbnail rendering in criteria input.",
            "implementationPlan": "Edit CriteresAutomatiquesInput.tsx",
        },
        context_pack={
            "candidate_files": [
                "admin/src/components/CriteresAutomatiquesInput.tsx",
                "admin/src/components/AuthorCard.tsx",
                "admin/src/services/AuthorService.ts",
            ]
        },
        code_review_payload={
            "filesModified": ["admin/src/components/CriteresAutomatiquesInput.tsx"],
            "filesCreated": ["admin/tests/components/CriteresAutomatiquesInput.test.tsx"],
            "scopeValidation": {"outcome": "PASS", "scopePrecision": 1.0},
            "testRun": {"passed": True},
        },
        files_modified=[
            "admin/src/components/CriteresAutomatiquesInput.tsx",
            "admin/tests/components/CriteresAutomatiquesInput.test.tsx",
        ],
    )

    payload = trace.to_dict()
    assert payload["overallConfidence"] >= 80
    assert payload["fileDecisions"]
    primary = payload["fileDecisions"][0]
    assert primary["path"].endswith("CriteresAutomatiquesInput.tsx")
    assert primary["why"]
    assert primary["confidence"] >= 80
    assert "AuthorCard.tsx" in payload["rejectedAlternatives"] or any(
        "AuthorCard.tsx" in alt for alt in primary["rejectedAlternatives"]
    )
    assert payload["riskAssessment"]["summary"]
    assert any("UI" in line for line in payload["riskAssessment"]["summary"])


def test_generate_mr_draft_content_includes_decision_trace():
    content = generate_mr_draft_content(
        jira_key="BN-516",
        work_order_title="Fix author thumbnail",
        jira_snapshot={"summary": "Fix author thumbnail", "description": "Acceptance criteria: vignette auteur"},
        approved_plan={
            "confidenceLevel": 0.87,
            "implementationPlan": "1. Edit component",
            "likelyImpactedFiles": ["admin/src/components/CriteresAutomatiquesInput.tsx"],
            "ticketUnderstanding": "Update author vignette rendering.",
        },
        context_pack={
            "candidate_files": [
                "admin/src/components/CriteresAutomatiquesInput.tsx",
                "admin/src/components/AuthorCard.tsx",
            ]
        },
        code_review_payload={
            "summary": "Updated criteria input handling.",
            "filesModified": ["admin/src/components/CriteresAutomatiquesInput.tsx"],
            "scopeValidation": {"outcome": "PASS", "scopePrecision": 1.0, "scopeRecall": 1.0},
            "testRun": {"passed": True},
        },
    )

    trace = content["decisionTrace"]
    assert trace["reasoningSummary"]
    assert trace["overallConfidence"] >= 70
    assert trace["fileDecisions"]
    assert "### Reasoning Summary" in content["description"]
    assert "Overall confidence" in content["description"]


def test_code_review_approve_to_explainable_mr_draft(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        record_id = _insert_ready_record(conn, jira_key="AAC-55")

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
    assert draft.decision_trace
    assert draft.decision_trace.get("reasoningSummary")
    assert mr_gate["payload"].get("decisionTrace")
    assert draft.decision_trace.get("fileDecisions") is not None


def test_mr_draft_still_blocks_gitlab_writes():
    reset_shadow_audit_log()
    violation = check_mcp_tool("gitlab", "create_merge_request")
    assert violation is not None
    assert get_shadow_audit_log().to_dict()["violationCount"] >= 1


@pytest.fixture(autouse=True)
def _shadow_env(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_SHADOW_MODE", "true")
    reset_shadow_audit_log()
