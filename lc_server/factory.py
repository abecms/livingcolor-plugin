"""LivingColor Server service wiring."""

from __future__ import annotations

import asyncio
from typing import Any

from delivery_runtime.api.deps import DeliveryServices
from delivery_runtime.events.store import EventStore
from delivery_runtime.gates.service import GateService
from delivery_runtime.orchestration.engine import OrchestrationEngine
from delivery_runtime.mr_drafts.service import MrDraftService
from delivery_runtime.pm_inbox.queue_consumer import ExecutionQueueConsumer
from delivery_runtime.pm_inbox.service import PmInboxService
from delivery_runtime.readiness.analyst_backend import AnalystBackend, SynchronousAnalystBackend
from delivery_runtime.readiness.scanner import ReadinessScanner
from delivery_runtime.readiness.service import ReadinessService
from delivery_runtime.work_orders.service import WorkOrderService
from lc_server.agent_bridge.hermes_analyst_subagent import (
    HermesSubagentAnalystBackend,
    default_subagent_launcher_available,
)
from lc_server.agent_bridge.hermes_runtime import get_agent_runtime_bridge
from lc_server.integrations.jira_estimate_invoker import McpJiraEstimateInvoker
from lc_server.integrations.jira_readiness import (
    fetch_issue_snapshot_for_readiness,
    fetch_issues_for_readiness,
)


def _analysis_runner(snapshot: dict[str, Any], project_key: str) -> dict[str, Any]:
    bridge = get_agent_runtime_bridge()
    jira_key = str(snapshot.get("key") or "")
    return asyncio.run(
        bridge.run_readiness_analysis(
            jira_key,
            {"projectKey": project_key, "snapshot": snapshot},
        )
    )


def _heuristic_analysis_runner(snapshot: dict[str, Any], project_key: str) -> dict[str, Any]:
    from delivery_runtime.readiness.analyzer import analyze_ticket_snapshot

    enriched = dict(snapshot)
    enriched.setdefault("projectKey", project_key)
    return analyze_ticket_snapshot(enriched)


def _build_readiness_analysis_backend() -> AnalystBackend:
    import os

    backend = os.getenv("LIVINGCOLOR_ANALYST_BACKEND", "hermes").strip().lower()
    if backend in {"heuristic", "stub", "deterministic"}:
        return SynchronousAnalystBackend(_heuristic_analysis_runner)

    if default_subagent_launcher_available():
        return HermesSubagentAnalystBackend(fallback_runner=_analysis_runner)
    return SynchronousAnalystBackend(_analysis_runner)


def build_delivery_services() -> DeliveryServices:
    """Construct server-owned delivery services with integrations injected."""
    events = EventStore()
    agent_bridge = get_agent_runtime_bridge()
    mr_drafts = MrDraftService(events)
    gates = GateService(
        events,
        mr_drafts=mr_drafts,
        jira_estimate_invoker_factory=McpJiraEstimateInvoker,
    )
    orchestrator = OrchestrationEngine(events, agent_bridge=agent_bridge, gate_service=gates)
    gates.bind_orchestrator(orchestrator)
    mr_drafts.bind_orchestrator(orchestrator)

    scanner = ReadinessScanner(
        events,
        issue_fetcher=fetch_issues_for_readiness,
        analysis_backend=_build_readiness_analysis_backend(),
    )
    work_orders = WorkOrderService(events)
    readiness = ReadinessService(
        events,
        scanner,
        work_orders,
        orchestrator=orchestrator,
        analysis_runner=_analysis_runner,
        issue_refresher=fetch_issue_snapshot_for_readiness,
    )
    queue_consumer = ExecutionQueueConsumer(
        events=events,
        work_orders=work_orders,
        readiness=readiness,
        orchestrator=orchestrator,
    )
    orchestrator.bind_queue_consumer(queue_consumer)
    pm_inbox = PmInboxService(events=events, scanner=scanner, queue_consumer=queue_consumer)

    return DeliveryServices(
        readiness=readiness,
        work_orders=work_orders,
        events=events,
        gates=gates,
        orchestrator=orchestrator,
        agent_bridge=agent_bridge,
        mr_drafts=mr_drafts,
        pm_inbox=pm_inbox,
        queue_consumer=queue_consumer,
    )
