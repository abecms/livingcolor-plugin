"""Push team-scoped delivery changes to the LivingColor cloud API."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from delivery_runtime.persistence.db import utc_now_iso
from delivery_runtime.persistence.pending_events import enqueue_pending_event
from lc_server.context import LOCAL_ORG_ID, get_request_bearer_token, require_project_context

logger = logging.getLogger(__name__)

CLOUD_API_BASE_URL = os.getenv("LIVINGCOLOR_CLOUD_API_URL", "https://api-livingcolor.visualq.ai").rstrip("/")


def _try_post_cloud_event(
    org_id: str,
    work_order_id: str,
    event_type: str,
    payload: dict[str, Any],
    bearer_token: str,
) -> bool:
    body = json.dumps(
        {
            "woId": work_order_id,
            "eventType": event_type,
            "payload": payload,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{CLOUD_API_BASE_URL}/v1/orgs/{org_id}/events",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "X-LC-Org-Id": org_id,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        logger.info("Cloud event POST failed (%s) for %s/%s", exc.code, org_id, work_order_id)
        return False
    except OSError as exc:
        logger.info("Cloud event POST unreachable for %s/%s: %s", org_id, work_order_id, exc)
        return False


def publish_team_delivery_event(
    *,
    work_order_id: str | None,
    event_type: str,
    payload: dict[str, Any] | None = None,
    include_work_order_snapshot: bool = True,
) -> None:
    """Mirror a local delivery event to Firestore via cloud API, or queue offline."""
    if not work_order_id:
        return

    ctx = require_project_context()
    org_id = ctx.normalized_org_id()
    if org_id == LOCAL_ORG_ID:
        return

    cloud_payload: dict[str, Any] = {
        "type": event_type,
        "eventType": event_type,
        "updatedAt": utc_now_iso(),
        **(payload or {}),
    }

    if include_work_order_snapshot:
        from delivery_runtime.work_orders.service import WorkOrderService

        snapshot = WorkOrderService().get_work_order(work_order_id)
        if snapshot:
            cloud_payload["workOrder"] = snapshot
            cloud_payload["updatedAt"] = snapshot.get("updatedAt") or cloud_payload["updatedAt"]

    bearer_token = get_request_bearer_token()
    if bearer_token and _try_post_cloud_event(org_id, work_order_id, event_type, cloud_payload, bearer_token):
        return

    enqueue_pending_event(org_id, work_order_id, cloud_payload)
