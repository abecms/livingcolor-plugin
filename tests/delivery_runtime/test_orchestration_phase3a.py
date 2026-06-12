"""Phase 3A orchestration and code review gate tests."""

from __future__ import annotations

from delivery_runtime.events.store import EventStore
from delivery_runtime.gates.constants import CODE_REVIEW_GATE_TYPE, GATE1_TYPE, MR_REVIEW_GATE_TYPE
from delivery_runtime.gates.service import GateService
from delivery_runtime.mr_drafts.service import MrDraftService
from delivery_runtime.orchestration.engine import OrchestrationEngine
from delivery_runtime.persistence.db import connect, init_db, json_dumps, next_public_id, utc_now_iso
from delivery_runtime.readiness.service import ReadinessService
from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping
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
    mr_drafts.bind_orchestrator(orchestrator)
    work_orders = WorkOrderService(events)
    readiness = ReadinessService(events, work_orders=work_orders, orchestrator=orchestrator)
    return readiness, work_orders, gates, events


def _insert_ready_record(conn, *, jira_key: str = "AAC-42") -> str:
    record_id = next_public_id(conn, "RD")
    now = utc_now_iso()
    snapshot = {
        "key": jira_key,
        "summary": "OAuth callback endpoint",
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


def test_approve_analysis_plan_runs_development_and_opens_code_review(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        record_id = _insert_ready_record(conn)

    readiness, work_orders, gates, events = _build_services()
    work_order = readiness.promote(record_id)
    analysis_gate_id = work_order["gates"][0]["id"]
    gates.approve(analysis_gate_id)

    updated = work_orders.get_work_order(work_order["id"])
    assert updated is not None
    assert updated["status"] == "awaiting_gate"
    assert updated["currentStage"] == "code_review"
    code_gate = next(g for g in updated["gates"] if g["gateType"] == CODE_REVIEW_GATE_TYPE)
    assert code_gate["status"] == "pending"
    assert code_gate["payload"]["diffPreview"]
    assert code_gate["payload"]["filesModified"] or code_gate["payload"]["filesCreated"]

    dev_node = next(node for node in updated["graphNodes"] if node["nodeType"] == "development")
    assert dev_node["status"] == "completed"
    assert dev_node["payload"]["patchArtifactPath"]
    assert dev_node["payload"].get("scopeValidation", {}).get("outcome") in {"PASS", "SCOPE_VIOLATION", "SCOPE_EXPLOSION"}

    qa_node = next(node for node in updated["graphNodes"] if node["nodeType"] == "qa_validation")
    assert qa_node["status"] == "completed"
    assert qa_node["payload"].get("phase") == "code_quality_review"
    assert qa_node["payload"].get("mergedWithDevelopment") is True

    from delivery_runtime.development.scope_store import load_scope_contract

    scope_contract = load_scope_contract(work_order["id"])
    assert scope_contract is not None
    assert scope_contract.allowed_files

    event_types = [event["eventType"] for event in events.list_for_work_order(work_order["id"], limit=30)]
    assert "GRAPH_NODE_STARTED" in event_types
    assert event_types.count("GATE_OPENED") == 2


def test_code_review_reject_regenerates_patch_with_structured_feedback(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        record_id = _insert_ready_record(conn, jira_key="AAC-43")

    readiness, work_orders, gates, _events = _build_services()
    work_order = readiness.promote(record_id)
    gates.approve(work_order["gates"][0]["id"])

    updated = work_orders.get_work_order(work_order["id"])
    assert updated is not None
    code_gate = next(g for g in updated["gates"] if g["gateType"] == CODE_REVIEW_GATE_TYPE)
    first_preview = code_gate["payload"]["diffPreview"]

    gates.reject(
        code_gate["id"],
        feedback="Handle null user state.",
        structured_feedback=[{"type": "missing_case", "message": "Handle null user state."}],
    )

    updated = work_orders.get_work_order(work_order["id"])
    assert updated is not None
    pending = next(g for g in updated["gates"] if g["gateType"] == CODE_REVIEW_GATE_TYPE and g["status"] == "pending")
    assert "Handle null user state" in pending["payload"]["diffPreview"]
    assert pending["payload"]["diffPreview"] != first_preview or len(updated["gates"]) > 2

    dev_node = next(node for node in updated["graphNodes"] if node["nodeType"] == "development")
    assert dev_node["payload"]["reviewerFeedbackApplied"]


def test_code_review_approve_generates_mr_draft_and_opens_mr_review_gate(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        record_id = _insert_ready_record(conn, jira_key="AAC-44")

    readiness, work_orders, gates, _events = _build_services()
    work_order = readiness.promote(record_id)
    gates.approve(work_order["gates"][0]["id"])

    updated = work_orders.get_work_order(work_order["id"])
    assert updated is not None
    code_gate = next(g for g in updated["gates"] if g["gateType"] == CODE_REVIEW_GATE_TYPE)
    gates.approve(code_gate["id"])

    updated = work_orders.get_work_order(work_order["id"])
    assert updated is not None
    assert updated["currentStage"] == "mr_draft"
    assert updated["status"] == "awaiting_gate"
    mr_gate = next(g for g in updated["gates"] if g["gateType"] == MR_REVIEW_GATE_TYPE and g["status"] == "pending")
    assert mr_gate["payload"]["draftId"]
    assert mr_gate["payload"]["title"]

    from delivery_runtime.mr_drafts.store import load_mr_draft

    draft = load_mr_draft(mr_gate["payload"]["draftId"])
    assert draft is not None
    assert draft.status == "awaiting_review"
    assert draft.files_modified

    mr_node = next(node for node in updated["graphNodes"] if node["nodeType"] == "mr_creation")
    # Real publication: the node stays pending until the MR draft is approved,
    # but it is stamped with the draft id for the publisher run.
    assert mr_node["status"] == "pending"
    assert mr_node["payload"]["draftId"] == draft.id
