"""Phase 2 orchestration and gate lifecycle tests."""

from __future__ import annotations

from delivery_runtime.events.store import EventStore
from delivery_runtime.gates.service import GateService
from delivery_runtime.orchestration.engine import OrchestrationEngine
from delivery_runtime.persistence.db import connect, init_db, json_dumps, next_public_id, utc_now_iso
from delivery_runtime.readiness.service import ReadinessService
from delivery_runtime.work_orders.service import WorkOrderService
from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping
from lc_server.agent_bridge.hermes_runtime import HermesRuntimeBridge


def _build_services():
    install_phase25_project_mapping()
    events = EventStore()
    bridge = HermesRuntimeBridge()
    gates = GateService(events)
    orchestrator = OrchestrationEngine(events, agent_bridge=bridge, gate_service=gates)
    gates.bind_orchestrator(orchestrator)
    work_orders = WorkOrderService(events)
    readiness = ReadinessService(events, work_orders=work_orders, orchestrator=orchestrator)
    return readiness, work_orders, gates, orchestrator, events


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
        ) VALUES (?, ?, ?, ?, 88, 'ready', 'Ready', '[]', ?, 0.88, ?, ?, ?, ?)
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


def test_promote_starts_plan_node_and_opens_analysis_gate(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        record_id = _insert_ready_record(conn)

    readiness, work_orders, _gates, _orchestrator, events = _build_services()
    work_order = readiness.promote(record_id)

    assert work_order["status"] == "awaiting_gate"
    assert work_order["currentStage"] == "analysis_review"
    assert len(work_order["gates"]) == 1
    gate = work_order["gates"][0]
    assert gate["gateType"] == "analysis_plan"
    assert gate["status"] == "pending"
    assert gate["payload"]["ticketUnderstanding"]
    assert gate["payload"]["implementationPlan"]
    assert gate["payload"]["targetRepo"] == "gitlab.com/org/app"
    assert gate["payload"]["likelyImpactedFiles"]
    assert not any("/**" in path for path in gate["payload"]["likelyImpactedFiles"])
    assert gate["payload"]["confidenceLevel"] > 0

    plan_node = next(node for node in work_order["graphNodes"] if node["nodeType"] == "implementation_plan")
    assert plan_node["status"] == "completed"

    event_types = [event["eventType"] for event in events.list_for_work_order(work_order["id"], limit=20)]
    assert "GRAPH_NODE_STARTED" in event_types
    assert "GRAPH_NODE_COMPLETED" in event_types
    assert "GATE_OPENED" in event_types


def test_gate_approve_closes_gate_and_moves_work_order_forward(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        record_id = _insert_ready_record(conn)

    readiness, work_orders, gates, _orchestrator, events = _build_services()
    work_order = readiness.promote(record_id)
    gate_id = work_order["gates"][0]["id"]

    result = gates.approve(gate_id, approved_by="human:test")
    assert result["gate"]["status"] == "approved"
    assert result["gate"]["approvedBy"] == "human:test"

    updated = work_orders.get_work_order(work_order["id"])
    assert updated is not None
    assert updated["status"] == "awaiting_gate"
    assert updated["currentStage"] == "code_review"
    assert updated["gates"][0]["status"] == "approved"

    event_types = [event["eventType"] for event in events.list_for_work_order(work_order["id"], limit=20)]
    assert "GATE_APPROVED" in event_types


def test_gate_reject_stores_feedback_and_reopens_plan_node(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        record_id = _insert_ready_record(conn)

    readiness, work_orders, gates, _orchestrator, events = _build_services()
    work_order = readiness.promote(record_id)
    gate_id = work_order["gates"][0]["id"]

    result = gates.reject(gate_id, feedback="Add migration plan for token storage", rejected_by="human:test")
    assert result["gate"]["status"] == "rejected"
    assert result["gate"]["rejectionFeedback"] == "Add migration plan for token storage"

    updated = work_orders.get_work_order(work_order["id"])
    assert updated is not None
    assert updated["status"] == "awaiting_gate"
    assert updated["currentStage"] == "analysis_review"
    assert len(updated["gates"]) == 2
    assert updated["gates"][0]["status"] == "rejected"
    assert updated["gates"][1]["status"] == "pending"
    assert "Add migration plan" in updated["gates"][1]["payload"]["ticketUnderstanding"]

    plan_node = next(node for node in updated["graphNodes"] if node["nodeType"] == "implementation_plan")
    assert plan_node["status"] == "completed"
    assert plan_node["payload"]["rejectionFeedback"] == "Add migration plan for token storage"

    event_types = [event["eventType"] for event in events.list_for_work_order(work_order["id"], limit=30)]
    assert event_types.count("GATE_OPENED") == 2
    assert "GATE_REJECTED" in event_types


def test_events_remain_append_only_after_gate_actions(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        record_id = _insert_ready_record(conn)

    readiness, _work_orders, gates, _orchestrator, events = _build_services()
    work_order = readiness.promote(record_id)
    gate_id = work_order["gates"][0]["id"]
    gates.approve(gate_id)

    with connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE work_order_id = ?",
            (work_order["id"],),
        ).fetchone()[0]
    listed = events.list_for_work_order(work_order["id"], limit=100)
    assert len(listed) == count
