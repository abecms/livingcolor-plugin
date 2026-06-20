"""Tests for Jira originalEstimate write-back at analysis approval."""

from delivery_runtime.events.store import EventStore
from delivery_runtime.gates.constants import GATE1_TYPE
from delivery_runtime.gates.service import GateService
from delivery_runtime.jira.estimate_writeback import write_estimate_to_jira
from delivery_runtime.persistence.db import (
    connect,
    init_db,
    json_dumps,
    next_public_id,
    utc_now_iso,
)


class FakeInvoker:
    def __init__(self, *, existing_estimate="", fail=False):
        self.calls = []
        self.existing_estimate = existing_estimate
        self.fail = fail

    def get_issue(self, issue_key):
        return {"fields": {"timetracking": {"originalEstimate": self.existing_estimate}}}

    def update_estimate(self, issue_key, estimate):
        if self.fail:
            raise RuntimeError("jira down")
        self.calls.append((issue_key, estimate))


def test_writes_estimate_when_field_empty():
    invoker = FakeInvoker()
    result = write_estimate_to_jira("TVP-1489", 1.5, invoker=invoker)
    assert result == {"written": True, "estimate": "1d 4h"}
    assert invoker.calls == [("TVP-1489", "1d 4h")]


def test_skips_when_field_already_set():
    invoker = FakeInvoker(existing_estimate="2d")
    result = write_estimate_to_jira("TVP-1489", 1.5, invoker=invoker)
    assert result == {"written": False, "reason": "already_set", "existingEstimate": "2d"}
    assert invoker.calls == []


def test_overwrites_when_field_already_set_and_overwrite_enabled():
    invoker = FakeInvoker(existing_estimate="2d")
    result = write_estimate_to_jira("TVP-1489", 1.5, invoker=invoker, overwrite=True)
    assert result == {
        "written": True,
        "estimate": "1d 4h",
        "overwritten": True,
        "previousEstimate": "2d",
    }
    assert invoker.calls == [("TVP-1489", "1d 4h")]


def test_failure_returns_error_does_not_raise():
    invoker = FakeInvoker(fail=True)
    result = write_estimate_to_jira("TVP-1489", 1.5, invoker=invoker)
    assert result["written"] is False
    assert "jira down" in result["reason"]


def test_skips_in_shadow_mode(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_SHADOW_MODE", "true")
    invoker = FakeInvoker()
    result = write_estimate_to_jira("TVP-1489", 1.5, invoker=invoker)
    assert result == {"written": False, "reason": "shadow_mode"}
    assert invoker.calls == []


def test_skips_when_no_estimate():
    invoker = FakeInvoker()
    result = write_estimate_to_jira("TVP-1489", None, invoker=invoker)
    assert result == {"written": False, "reason": "no_estimate"}


def _seed_analysis_gate(conn, *, jira_key: str = "TVP-1489", estimated_days: float | None = 1.5) -> str:
    """Insert a readiness record, a linked work order, and a pending Gate 1."""
    now = utc_now_iso()
    readiness_id = next_public_id(conn, "RD")
    conn.execute(
        """
        INSERT INTO readiness_records (
            id, jira_key, project_key, title, readiness_score, readiness_status,
            analysis_summary, blockers_json, recommended_repos_json, confidence,
            estimated_days, jira_snapshot_json, analyzed_at, created_at, updated_at
        ) VALUES (?, ?, 'TVP', 'Fix checkout', 85, 'promoted', 'Ready', '[]', '[]', 0.8,
                  ?, ?, ?, ?, ?)
        """,
        (
            readiness_id,
            jira_key,
            estimated_days,
            json_dumps({"key": jira_key, "summary": "Fix checkout", "issueType": "Bug"}),
            now,
            now,
            now,
        ),
    )
    work_order_id = next_public_id(conn, "WO")
    conn.execute(
        """
        INSERT INTO work_orders (
            id, jira_key, readiness_id, title, status, current_stage, created_at, updated_at
        ) VALUES (?, ?, ?, 'Fix checkout', 'awaiting_gate', 'analysis_review', ?, ?)
        """,
        (work_order_id, jira_key, readiness_id, now, now),
    )
    gate_id = next_public_id(conn, "GT")
    conn.execute(
        """
        INSERT INTO gates (id, work_order_id, gate_type, status, payload_json, created_at)
        VALUES (?, ?, ?, 'pending', '{}', ?)
        """,
        (gate_id, work_order_id, GATE1_TYPE, now),
    )
    return gate_id


def test_gate_approval_writes_persisted_estimate_once(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        gate_id = _seed_analysis_gate(conn, estimated_days=1.5)

    invoker = FakeInvoker()
    events = EventStore()
    gates = GateService(events, jira_estimate_invoker_factory=lambda: invoker)

    result = gates.approve(gate_id, approved_by="human:test")

    assert result["gate"]["status"] == "approved"
    assert invoker.calls == [("TVP-1489", "1d 4h")]
    assert result["jiraEstimateWriteback"] == {
        "jiraKey": "TVP-1489",
        "written": True,
        "estimate": "1d 4h",
    }

    event_types = [event["eventType"] for event in events.list_for_work_order(result["workOrderId"], limit=20)]
    assert event_types.count("JIRA_ESTIMATE_WRITTEN") == 1
    written = next(
        event
        for event in events.list_for_work_order(result["workOrderId"], limit=20)
        if event["eventType"] == "JIRA_ESTIMATE_WRITTEN"
    )
    assert written["payload"] == {"jiraKey": "TVP-1489", "written": True, "estimate": "1d 4h"}


def test_gate_approval_succeeds_when_invoker_raises(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        gate_id = _seed_analysis_gate(conn)

    invoker = FakeInvoker(fail=True)
    events = EventStore()
    gates = GateService(events, jira_estimate_invoker_factory=lambda: invoker)

    result = gates.approve(gate_id, approved_by="human:test")

    assert result["gate"]["status"] == "approved"
    event_types = [event["eventType"] for event in events.list_for_work_order(result["workOrderId"], limit=20)]
    assert "JIRA_ESTIMATE_WRITE_FAILED" in event_types
    assert "JIRA_ESTIMATE_WRITTEN" not in event_types


def test_gate_approval_overwrites_existing_jira_estimate(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        gate_id = _seed_analysis_gate(conn, estimated_days=1.5)

    invoker = FakeInvoker(existing_estimate="2d")
    events = EventStore()
    gates = GateService(events, jira_estimate_invoker_factory=lambda: invoker)

    result = gates.approve(gate_id, approved_by="human:test")

    assert result["gate"]["status"] == "approved"
    assert invoker.calls == [("TVP-1489", "1d 4h")]
    assert result["jiraEstimateWriteback"]["written"] is True
    assert result["jiraEstimateWriteback"]["overwritten"] is True


def test_gate_approval_falls_back_to_heuristic_estimate(_isolate_hermes_home):
    init_db()
    with connect() as conn:
        gate_id = _seed_analysis_gate(conn, estimated_days=None)

    invoker = FakeInvoker()
    events = EventStore()
    gates = GateService(events, jira_estimate_invoker_factory=lambda: invoker)

    result = gates.approve(gate_id, approved_by="human:test")

    assert result["gate"]["status"] == "approved"
    assert len(invoker.calls) == 1
    issue_key, estimate = invoker.calls[0]
    assert issue_key == "TVP-1489"
    assert estimate  # heuristic produced a non-empty Jira estimate string
    event_types = [event["eventType"] for event in events.list_for_work_order(result["workOrderId"], limit=20)]
    assert "JIRA_ESTIMATE_WRITTEN" in event_types
