from __future__ import annotations

from unittest.mock import patch

from delivery_runtime.persistence.db import init_db
from lc_server.context import LOCAL_ORG_ID, ProjectContext, reset_project_context, set_project_context
from lc_server.integrations.cloud_sync import publish_team_delivery_event


def test_publish_team_delivery_event_enqueues_when_cloud_unreachable(tmp_path, monkeypatch):
    db_path = tmp_path / "runtime.db"
    monkeypatch.setattr("delivery_runtime.persistence.db.get_delivery_db_path", lambda: db_path)
    init_db(db_path)

    context_token = set_project_context(ProjectContext(org_id="team-1", project_key="BN"))
    try:
        with patch("lc_server.integrations.cloud_sync._try_post_cloud_event", return_value=False):
            publish_team_delivery_event(
                work_order_id="WO-1",
                event_type="GATE_APPROVED",
                payload={"gateId": "G-1"},
                include_work_order_snapshot=False,
            )
    finally:
        reset_project_context(context_token)

    from delivery_runtime.persistence.pending_events import list_pending_events

    pending = list_pending_events("team-1")
    assert len(pending) == 1
    assert pending[0]["woId"] == "WO-1"
    assert pending[0]["payload"]["eventType"] == "GATE_APPROVED"


def test_publish_team_delivery_event_skips_local_workspace(tmp_path, monkeypatch):
    db_path = tmp_path / "runtime.db"
    monkeypatch.setattr("delivery_runtime.persistence.db.get_delivery_db_path", lambda: db_path)
    init_db(db_path)

    context_token = set_project_context(ProjectContext(org_id=LOCAL_ORG_ID, project_key="BN"))
    try:
        publish_team_delivery_event(work_order_id="WO-1", event_type="GATE_APPROVED")
    finally:
        reset_project_context(context_token)

    from delivery_runtime.persistence.pending_events import list_pending_events

    assert list_pending_events("local") == []
