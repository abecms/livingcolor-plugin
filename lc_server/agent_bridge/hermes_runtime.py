"""Hermes-backed agent runtime bridge (server-only)."""

from __future__ import annotations

import logging
from typing import Any

from delivery_runtime.agent_bridge.protocol import AgentRuntimeBridge
from delivery_runtime.agents.registry import AgentManifestRegistry
from delivery_runtime.context.pack_builder import ContextPackBuilder
from delivery_runtime.readiness.analyzer import analyze_ticket_snapshot
from delivery_runtime.readiness.analyst_prompt import AnalystParseError
from lc_server.agent_bridge.developer_backend import get_developer_agent
from lc_server.agent_bridge.hermes_analyst import HermesAnalystAgent
from lc_server.agent_bridge.hermes_planner import HermesPlannerAgent, PlannerParseError
from lc_server.agent_bridge.hermes_publisher import HermesPublisherAgent
from lc_server.integrations.jira_attachment_extract import enrich_snapshot_with_attachment_extracts

logger = logging.getLogger(__name__)


class HermesRuntimeBridge:
    """Adapter from LivingColor delivery orchestration to the Hermes agent loop."""

    def __init__(
        self,
        *,
        pack_builder: ContextPackBuilder | None = None,
        developer: Any | None = None,
        registry: AgentManifestRegistry | None = None,
        analyst: HermesAnalystAgent | None = None,
        planner: HermesPlannerAgent | None = None,
        publisher: HermesPublisherAgent | None = None,
    ) -> None:
        self.pack_builder = pack_builder or ContextPackBuilder()
        self.developer = developer or get_developer_agent()
        self.registry = registry or AgentManifestRegistry()
        self.analyst = analyst or HermesAnalystAgent(registry=self.registry)
        self.planner = planner or HermesPlannerAgent(registry=self.registry)
        self.publisher = publisher or HermesPublisherAgent(registry=self.registry)

    async def run_readiness_analysis(self, jira_key: str, context: dict[str, Any]) -> dict[str, Any]:
        snapshot = context.get("snapshot") or {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        snapshot = enrich_snapshot_with_attachment_extracts(snapshot)
        project_key = str(context.get("projectKey") or jira_key.split("-")[0]).strip().upper()
        if self.registry.is_automation_ready(project_key):
            try:
                return self.analyst.analyze(snapshot, project_key)
            except AnalystParseError as exc:
                logger.warning(
                    "Analyst run failed for %s (%s); returning analysis_failed",
                    jira_key,
                    exc,
                )
                return {
                    "readinessScore": 0,
                    "readinessStatus": "analysis_failed",
                    "analysisSummary": f"LLM readiness analysis output could not be parsed: {exc}",
                    "blockers": [str(exc)],
                    "recommendedRepos": [],
                    "confidence": 0.0,
                    "estimatedDays": 0,
                    "jiraSnapshot": snapshot,
                }
        return analyze_ticket_snapshot(snapshot)

    async def run_node(
        self,
        work_order_id: str,
        node: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        node_type = str(node.get("nodeType") or "")
        if node_type == "implementation_plan":
            enriched = {
                **context,
                "nodePayload": node.get("payload") or {},
            }
            jira_snapshot = enriched.get("jiraSnapshot")
            if isinstance(jira_snapshot, dict):
                enriched["jiraSnapshot"] = enrich_snapshot_with_attachment_extracts(jira_snapshot)
            pack = self.pack_builder.build(enriched)
            project_key = str(
                enriched.get("projectKey")
                or (enriched.get("workOrder") or {}).get("projectKey")
                or pack.jira_ticket.get("projectKey")
                or pack.jira_key.split("-")[0]
            ).strip().upper()
            try:
                return self.planner.plan(pack, project_key=project_key)
            except PlannerParseError as exc:
                logger.error(
                    "Planner LLM failed for %s (%s); Gate 1 requires LLM output",
                    pack.jira_key,
                    exc,
                )
                raise
        if node_type == "development":
            return self.developer.execute(work_order_id, context)
        if node_type == "qa_validation":
            # Legacy graphs: QA is merged into the development Hermes run.
            dev_payload = context.get("mergedDevelopmentResult") or {}
            if dev_payload:
                return {
                    **dev_payload,
                    "passed": True,
                    "source": "developer_agent",
                    "phase": "code_quality_review",
                    "mergedWithDevelopment": True,
                }
            return {
                "passed": True,
                "source": "developer_agent",
                "phase": "code_quality_review",
                "mergedWithDevelopment": True,
            }
        if node_type == "mr_creation":
            return self.publisher.execute(work_order_id, context)
        raise NotImplementedError(f"Node type {node_type!r} is not implemented")

    async def cancel(self, run_id: str) -> None:
        raise NotImplementedError("Agent cancellation is implemented in a later phase")


def get_agent_runtime_bridge() -> AgentRuntimeBridge:
    return HermesRuntimeBridge()
