"""Slash command and model tools for the LivingColor plugin.

Runs in the Hermes agent process (CLI / gateway). Reuses the delivery
route functions directly so contracts match the HTTP API exactly. The
agent process never runs orchestration — it reads and writes records the
dashboard-process engine picks up (shared SQLite, WAL).
"""
from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)


def _ensure_services():
    """Wire delivery services lazily in this process (idempotent)."""
    from delivery_runtime.api import deps

    try:
        return deps.get_services()
    except Exception:
        from delivery_runtime.persistence.db import init_db
        from lc_server.factory import build_delivery_services

        init_db()
        deps.configure(build_delivery_services())
        return deps.get_services()


# -- tool handlers ----------------------------------------------------------


def tool_overview(args: dict, **kwargs) -> str:
    _ensure_services()
    from delivery_runtime.api.routes import get_delivery_overview

    return json.dumps(get_delivery_overview().model_dump(mode="json"))


def tool_scan_readiness(args: dict, **kwargs) -> str:
    _ensure_services()
    from delivery_runtime.api.routes import scan_readiness
    from delivery_runtime.api.schemas import ReadinessScanRequest

    body = ReadinessScanRequest(projectKey=args["project_key"])
    result = asyncio.run(scan_readiness(body))
    return json.dumps(result.model_dump(mode="json"))


def tool_promote(args: dict, **kwargs) -> str:
    _ensure_services()
    from delivery_runtime.api.routes import promote_readiness

    return json.dumps(promote_readiness(args["record_id"]).model_dump(mode="json"))


def tool_gate_decision(args: dict, **kwargs) -> str:
    _ensure_services()
    from delivery_runtime.api.routes import approve_gate, reject_gate

    if args["decision"] == "approve":
        result = approve_gate(args["gate_id"])
    else:
        result = reject_gate(args["gate_id"], None)
    return json.dumps(result.model_dump(mode="json"))


def tool_work_order_status(args: dict, **kwargs) -> str:
    _ensure_services()
    from delivery_runtime.api.routes import get_work_order

    return json.dumps(get_work_order(args["work_order_id"]).model_dump(mode="json"))


# -- slash command ----------------------------------------------------------

_USAGE = (
    "/delivery status | scan <PROJECT> | queue | promote <id> | gates"
)


def delivery_command(raw_args: str) -> str:
    parts = raw_args.split()
    sub = parts[0] if parts else "status"
    try:
        _ensure_services()
        from delivery_runtime.api import routes

        if sub == "status":
            data = routes.get_delivery_overview().model_dump(mode="json")
            return "Delivery overview:\n" + json.dumps(data, indent=2)[:1500]
        if sub == "scan" and len(parts) >= 2:
            return tool_scan_readiness({"project_key": parts[1]})
        if sub == "queue":
            data = routes.list_readiness(None, None).model_dump(mode="json")
            return "Readiness queue:\n" + json.dumps(data, indent=2)[:1500]
        if sub == "promote" and len(parts) >= 2:
            return tool_promote({"record_id": parts[1]})
        if sub == "gates":
            data = routes.list_recent_events(20).model_dump(mode="json")
            return "Recent delivery events:\n" + json.dumps(data, indent=2)[:1500]
        return _USAGE
    except Exception as exc:
        logger.exception("/delivery %s failed", sub)
        return f"delivery error: {exc}"


# -- registration -----------------------------------------------------------

_STR = {"type": "string"}


def register_surfaces(ctx) -> None:
    ctx.register_command(
        "delivery",
        delivery_command,
        description="LivingColor delivery platform (status, scan, queue, promote, gates)",
        args_hint="status|scan <PROJECT>|queue|promote <id>|gates",
    )
    ctx.register_tool(
        name="delivery_overview",
        toolset="livingcolor",
        schema={"type": "object", "properties": {}, "required": []},
        handler=tool_overview,
        description="Snapshot of the LivingColor delivery platform: work orders, readiness queue, pending gates.",
    )
    ctx.register_tool(
        name="delivery_scan_readiness",
        toolset="livingcolor",
        schema={"type": "object", "properties": {"project_key": _STR}, "required": ["project_key"]},
        handler=tool_scan_readiness,
        description="Scan a Jira project's issues into the delivery readiness queue. Does not mutate Jira.",
    )
    ctx.register_tool(
        name="delivery_promote",
        toolset="livingcolor",
        schema={"type": "object", "properties": {"record_id": _STR}, "required": ["record_id"]},
        handler=tool_promote,
        description="Promote a readiness record to a Work Order (explicit human-equivalent action).",
    )
    ctx.register_tool(
        name="delivery_gate_decision",
        toolset="livingcolor",
        schema={
            "type": "object",
            "properties": {"gate_id": _STR, "decision": {"type": "string", "enum": ["approve", "reject"]}},
            "required": ["gate_id", "decision"],
        },
        handler=tool_gate_decision,
        description="Approve or reject a paused delivery gate.",
    )
    ctx.register_tool(
        name="delivery_work_order_status",
        toolset="livingcolor",
        schema={"type": "object", "properties": {"work_order_id": _STR}, "required": ["work_order_id"]},
        handler=tool_work_order_status,
        description="Fetch a Work Order's current stage, status and metadata.",
    )

    from livingcolor_pm_tools import PM_TOOL_REGISTRATIONS

    for spec in PM_TOOL_REGISTRATIONS:
        ctx.register_tool(
            name=spec["name"],
            toolset="livingcolor",
            schema=spec["schema"],
            handler=spec["handler"],
            description=spec["description"],
        )
