"""MR draft approval enqueues real mr_creation publication."""

from __future__ import annotations

import pytest

from delivery_runtime.gates.constants import CODE_REVIEW_GATE_TYPE
from delivery_runtime.mr_drafts.service import MrDraftService
from delivery_runtime.persistence.db import (
    connect,
    init_db,
    json_dumps,
    json_loads,
    next_public_id,
    utc_now_iso,
)

# Captured before the seeding fixture monkeypatches it away.
_REAL_MAYBE_REQUEUE = MrDraftService._maybe_requeue_merge_conflicts


@pytest.fixture
def seeded_work_order_after_code_review(monkeypatch, tmp_path):
    """Work order with development/qa completed and mr_creation/jira_update pending."""
    monkeypatch.setattr(
        MrDraftService,
        "_maybe_requeue_merge_conflicts",
        lambda self, work_order_id: None,
    )
    init_db()
    now = utc_now_iso()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with connect() as conn:
        wo_id = next_public_id(conn, "WO")
        conn.execute(
            """
            INSERT INTO work_orders (
                id, jira_key, title, description, priority, status, current_stage,
                confidence, created_at, updated_at
            ) VALUES (?, 'AAC-77', 'Fix OAuth callback', '', 'High', 'running', 'code_review', 0.8, ?, ?)
            """,
            (wo_id, now, now),
        )

        plan_id = next_public_id(conn, "GN")
        dev_id = next_public_id(conn, "GN")
        qa_id = next_public_id(conn, "GN")
        mr_id = next_public_id(conn, "GN")
        jira_id = next_public_id(conn, "GN")
        dev_payload = {
            "workspacePath": str(workspace),
            "deliveryBranch": "feature/AAC-77",
            "integrationBranch": "main",
            "mergeTargetBranch": "develop",
            "summary": "Persist OAuth tokens after callback.",
            "filesModified": ["src/auth/oauth_callback.ts"],
            "patchStats": {"linesChanged": 12},
        }
        nodes = (
            (plan_id, "implementation_plan", "completed", [], {"contextPack": {}}),
            (dev_id, "development", "completed", [plan_id], dev_payload),
            (qa_id, "qa_validation", "completed", [dev_id], {"passed": True}),
            (mr_id, "mr_creation", "pending", [qa_id], {}),
            (jira_id, "jira_update", "pending", [mr_id], {}),
        )
        for node_id, node_type, status, deps, payload in nodes:
            conn.execute(
                """
                INSERT INTO graph_nodes (
                    id, work_order_id, node_type, status, depends_on_json,
                    payload_json, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_id,
                    wo_id,
                    node_type,
                    status,
                    json_dumps(deps),
                    json_dumps(payload),
                    now if status == "completed" else None,
                ),
            )

        gate_id = next_public_id(conn, "G")
        conn.execute(
            """
            INSERT INTO gates (
                id, work_order_id, gate_type, status, payload_json,
                created_at, approved_at, approved_by
            ) VALUES (?, ?, ?, 'approved', ?, ?, ?, 'human')
            """,
            (
                gate_id,
                wo_id,
                CODE_REVIEW_GATE_TYPE,
                json_dumps(
                    {
                        "summary": "Patch approved in code review.",
                        "filesModified": ["src/auth/oauth_callback.ts"],
                        "scopeValidation": {"outcome": "PASS"},
                        "testRun": {"passed": True},
                    }
                ),
                now,
                now,
            ),
        )
    return wo_id, gate_id


def _node_status(work_order_id, node_type):
    with connect() as conn:
        row = conn.execute(
            "SELECT status FROM graph_nodes WHERE work_order_id = ? AND node_type = ?",
            (work_order_id, node_type),
        ).fetchone()
    return row["status"] if row else None


def test_draft_creation_keeps_mr_creation_pending(seeded_work_order_after_code_review):
    wo_id, code_review_gate_id = seeded_work_order_after_code_review
    service = MrDraftService()
    service.create_draft_after_code_review(wo_id, code_review_gate_id=code_review_gate_id)
    assert _node_status(wo_id, "mr_creation") == "pending"


def test_draft_creation_completes_node_in_shadow_mode(seeded_work_order_after_code_review, monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_SHADOW_MODE", "true")
    wo_id, code_review_gate_id = seeded_work_order_after_code_review
    service = MrDraftService()
    service.create_draft_after_code_review(wo_id, code_review_gate_id=code_review_gate_id)
    assert _node_status(wo_id, "mr_creation") == "completed"


def test_approve_draft_sets_mr_publication_stage(seeded_work_order_after_code_review):
    wo_id, code_review_gate_id = seeded_work_order_after_code_review
    service = MrDraftService()
    draft = service.create_draft_after_code_review(wo_id, code_review_gate_id=code_review_gate_id)
    service.approve_draft(draft.id)
    with connect() as conn:
        row = conn.execute("SELECT current_stage FROM work_orders WHERE id = ?", (wo_id,)).fetchone()
    assert row["current_stage"] == "mr_publication"


def test_orchestrator_runs_publisher_for_mr_creation(seeded_work_order_after_code_review, monkeypatch):
    from delivery_runtime.events.store import EventStore
    from delivery_runtime.orchestration.engine import OrchestrationEngine

    wo_id, code_review_gate_id = seeded_work_order_after_code_review
    service = MrDraftService()
    draft = service.create_draft_after_code_review(wo_id, code_review_gate_id=code_review_gate_id)

    captured = {}

    class FakeBridge:
        async def run_node(self, work_order_id, node, context):
            captured["nodeType"] = node["nodeType"]
            captured["context"] = context
            return {
                "mrUrl": "https://gitlab.example.com/g/p/-/merge_requests/7",
                "mrIid": 7,
                "targetBranch": "develop",
                "status": "published",
            }

    engine = OrchestrationEngine(EventStore(), agent_bridge=FakeBridge())
    service.bind_orchestrator(engine)
    service.approve_draft(draft.id)

    assert captured["nodeType"] == "mr_creation"
    assert captured["context"]["draftId"] == draft.id
    assert captured["context"]["deliveryBranch"] == "feature/AAC-77"
    assert captured["context"]["workspacePath"]
    assert _node_status(wo_id, "mr_creation") == "completed"


def test_successful_publication_opens_jira_update_gate(seeded_work_order_after_code_review):
    from delivery_runtime.events.store import EventStore
    from delivery_runtime.gates.constants import JIRA_UPDATE_GATE_TYPE
    from delivery_runtime.gates.service import GateService
    from delivery_runtime.orchestration.engine import OrchestrationEngine

    wo_id, code_review_gate_id = seeded_work_order_after_code_review
    service = MrDraftService()
    draft = service.create_draft_after_code_review(wo_id, code_review_gate_id=code_review_gate_id)

    class FakeBridge:
        async def run_node(self, work_order_id, node, context):
            return {
                "mrUrl": "https://gitlab.example.com/g/p/-/merge_requests/7",
                "mrIid": 7,
                "targetBranch": "develop",
                "status": "published",
            }

    events = EventStore()
    engine = OrchestrationEngine(events, agent_bridge=FakeBridge())
    gates = GateService(events, orchestrator=engine)
    service.bind_orchestrator(engine)
    service.approve_draft(draft.id)

    with connect() as conn:
        wo_row = conn.execute(
            "SELECT status, current_stage FROM work_orders WHERE id = ?",
            (wo_id,),
        ).fetchone()
        jira_gate = conn.execute(
            """
            SELECT gate_type, status, payload_json FROM gates
            WHERE work_order_id = ? AND gate_type = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (wo_id, JIRA_UPDATE_GATE_TYPE),
        ).fetchone()

    assert wo_row["status"] == "awaiting_gate"
    assert wo_row["current_stage"] == "jira_review"
    assert jira_gate is not None
    assert jira_gate["status"] == "pending"
    payload = json_loads(jira_gate["payload_json"], {})
    assert payload["mrUrl"].endswith("/merge_requests/7")
    assert payload["proposedComment"]

    with connect() as conn:
        gate_row = conn.execute(
            "SELECT id FROM gates WHERE work_order_id = ? AND gate_type = ? AND status = 'pending'",
            (wo_id, JIRA_UPDATE_GATE_TYPE),
        ).fetchone()
    gates.approve(str(gate_row["id"]))

    with connect() as conn:
        wo_row = conn.execute(
            "SELECT status, current_stage FROM work_orders WHERE id = ?",
            (wo_id,),
        ).fetchone()
        jira_node = conn.execute(
            "SELECT status FROM graph_nodes WHERE work_order_id = ? AND node_type = 'jira_update'",
            (wo_id,),
        ).fetchone()

    assert wo_row["status"] == "completed"
    assert wo_row["current_stage"] == "completed"
    assert jira_node["status"] == "completed"


def test_publication_context_derives_delivery_branch_from_issue_type(seeded_work_order_after_code_review):
    """Legacy work orders without deliveryBranch in the dev payload derive it from the snapshot."""
    from delivery_runtime.events.store import EventStore
    from delivery_runtime.orchestration.engine import OrchestrationEngine
    from delivery_runtime.persistence.db import json_loads

    wo_id, code_review_gate_id = seeded_work_order_after_code_review
    service = MrDraftService()
    draft = service.create_draft_after_code_review(wo_id, code_review_gate_id=code_review_gate_id)

    now = utc_now_iso()
    with connect() as conn:
        record_id = next_public_id(conn, "RD")
        conn.execute(
            """
            INSERT INTO readiness_records (
                id, jira_key, project_key, title, readiness_score, readiness_status,
                analysis_summary, blockers_json, recommended_repos_json, confidence,
                jira_snapshot_json, analyzed_at, created_at, updated_at
            ) VALUES (?, 'AAC-77', 'AAC', 'Fix OAuth callback', 88, 'ready', '', '[]', '[]', 0.88, ?, ?, ?, ?)
            """,
            (record_id, json_dumps({"key": "AAC-77", "issueType": "Bug"}), now, now, now),
        )
        conn.execute(
            "UPDATE work_orders SET readiness_id = ? WHERE id = ?",
            (record_id, wo_id),
        )
        dev_row = conn.execute(
            "SELECT id, payload_json FROM graph_nodes WHERE work_order_id = ? AND node_type = 'development'",
            (wo_id,),
        ).fetchone()
        payload = json_loads(dev_row["payload_json"], {})
        payload.pop("deliveryBranch", None)
        conn.execute(
            "UPDATE graph_nodes SET payload_json = ? WHERE id = ?",
            (json_dumps(payload), dev_row["id"]),
        )

    engine = OrchestrationEngine(EventStore(), agent_bridge=None)
    with connect() as conn:
        context = engine._load_publication_context(conn, wo_id, {"draftId": draft.id})

    assert context["deliveryBranch"] == "fix/AAC-77"


def test_publication_context_fails_fast_when_draft_missing(seeded_work_order_after_code_review):
    import pytest as _pytest

    from delivery_runtime.events.store import EventStore
    from delivery_runtime.orchestration.engine import OrchestrationEngine

    wo_id, _gate_id = seeded_work_order_after_code_review
    engine = OrchestrationEngine(EventStore(), agent_bridge=None)
    with connect() as conn:
        with _pytest.raises(RuntimeError, match="draft"):
            engine._load_publication_context(conn, wo_id, {})


def test_tick_marks_mr_creation_failed_when_draft_missing(seeded_work_order_after_code_review):
    from delivery_runtime.events.store import EventStore
    from delivery_runtime.orchestration.engine import OrchestrationEngine
    from delivery_runtime.persistence.db import json_loads

    wo_id, code_review_gate_id = seeded_work_order_after_code_review
    service = MrDraftService()
    draft = service.create_draft_after_code_review(wo_id, code_review_gate_id=code_review_gate_id)
    service.approve_draft(draft.id)

    with connect() as conn:
        conn.execute(
            "UPDATE graph_nodes SET payload_json = '{}' WHERE work_order_id = ? AND node_type = 'mr_creation'",
            (wo_id,),
        )

    class ExplodingBridge:
        async def run_node(self, work_order_id, node, context):
            raise AssertionError("publisher must not run without a draft")

    engine = OrchestrationEngine(EventStore(), agent_bridge=ExplodingBridge())
    engine.tick(wo_id)

    with connect() as conn:
        node_row = conn.execute(
            "SELECT status, payload_json FROM graph_nodes WHERE work_order_id = ? AND node_type = 'mr_creation'",
            (wo_id,),
        ).fetchone()
        wo_row = conn.execute(
            "SELECT status, current_stage FROM work_orders WHERE id = ?",
            (wo_id,),
        ).fetchone()

    assert node_row["status"] == "failed"
    assert "no MR draft" in json_loads(node_row["payload_json"], {}).get("error", "")
    assert wo_row["current_stage"] == "mr_publication"


def test_failed_mr_creation_keeps_draft_id_in_payload(seeded_work_order_after_code_review):
    from delivery_runtime.events.store import EventStore
    from delivery_runtime.orchestration.engine import OrchestrationEngine
    from delivery_runtime.persistence.db import json_loads

    wo_id, code_review_gate_id = seeded_work_order_after_code_review
    service = MrDraftService()
    draft = service.create_draft_after_code_review(wo_id, code_review_gate_id=code_review_gate_id)

    class FailingBridge:
        async def run_node(self, work_order_id, node, context):
            raise RuntimeError("push rejected")

    engine = OrchestrationEngine(EventStore(), agent_bridge=FailingBridge())
    service.bind_orchestrator(engine)
    service.approve_draft(draft.id)

    with connect() as conn:
        node_row = conn.execute(
            "SELECT status, payload_json FROM graph_nodes WHERE work_order_id = ? AND node_type = 'mr_creation'",
            (wo_id,),
        ).fetchone()
        wo_row = conn.execute(
            "SELECT status, current_stage FROM work_orders WHERE id = ?",
            (wo_id,),
        ).fetchone()

    assert node_row["status"] == "failed"
    payload = json_loads(node_row["payload_json"], {})
    assert payload["draftId"] == draft.id
    assert "push rejected" in payload["error"]
    assert wo_row["status"] == "failed"
    assert wo_row["current_stage"] == "mr_publication"


def _approve_with_real_requeue(seeded, monkeypatch, merge_result):
    """Approve a draft with the real requeue logic and a stubbed merge attempt."""
    from delivery_runtime.development import merge_conflicts
    from delivery_runtime.events.store import EventStore

    wo_id, code_review_gate_id = seeded
    monkeypatch.setattr(MrDraftService, "_maybe_requeue_merge_conflicts", _REAL_MAYBE_REQUEUE)
    monkeypatch.setattr(
        merge_conflicts,
        "attempt_merge_into_target_branch",
        lambda workspace, **kwargs: merge_result,
    )

    events = EventStore()
    service = MrDraftService(events)
    draft = service.create_draft_after_code_review(wo_id, code_review_gate_id=code_review_gate_id)
    service.approve_draft(draft.id)

    with connect() as conn:
        wo_row = conn.execute(
            "SELECT current_stage FROM work_orders WHERE id = ?",
            (wo_id,),
        ).fetchone()
    event_types = [event["eventType"] for event in events.list_for_work_order(wo_id, limit=50)]
    return wo_row["current_stage"], event_types


def test_missing_merge_target_branch_does_not_requeue(seeded_work_order_after_code_review, monkeypatch):
    from delivery_runtime.development.merge_conflicts import MergeAttemptResult

    stage, event_types = _approve_with_real_requeue(
        seeded_work_order_after_code_review,
        monkeypatch,
        MergeAttemptResult(
            ok=False,
            message=(
                "No merge target branch found in /tmp/repo; "
                "expected one of: staging, dev, develop, preprod, test"
            ),
        ),
    )

    assert "MERGE_CONFLICT_REQUEUE" not in event_types
    assert stage == "mr_publication"


def test_genuine_merge_conflicts_still_requeue(seeded_work_order_after_code_review, monkeypatch):
    from delivery_runtime.development.merge_conflicts import MergeAttemptResult
    from delivery_runtime.development.phases import WORK_ORDER_STAGE_MERGE_CONFLICT_RESOLUTION

    stage, event_types = _approve_with_real_requeue(
        seeded_work_order_after_code_review,
        monkeypatch,
        MergeAttemptResult(
            ok=False,
            merge_target_branch="develop",
            feature_branch="feature/AAC-77",
            conflicting_files=["a.js"],
            message="Merge conflicts detected",
        ),
    )

    assert "MERGE_CONFLICT_REQUEUE" in event_types
    assert stage == WORK_ORDER_STAGE_MERGE_CONFLICT_RESOLUTION
