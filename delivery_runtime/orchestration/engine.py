"""Delivery orchestration loop — schedule nodes and pause at gates."""

from __future__ import annotations

import asyncio
from typing import Any

from delivery_runtime.events.store import EventStore
from delivery_runtime.execution_graph.scheduler import (
    find_ready_nodes,
    has_pending_gate,
    mark_node_completed,
    mark_node_running,
    refresh_node_readiness,
)
from delivery_runtime.gates.constants import (
    CLARIFICATION_GATE_TYPE,
    CODE_REVIEW_GATE_TYPE,
    GATE1_TYPE,
    JIRA_UPDATE_GATE_TYPE,
)
from delivery_runtime.persistence.db import connect, json_dumps, json_loads, next_public_id, utc_now_iso
from delivery_runtime.development.phases import (
    DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION,
    WORK_ORDER_STAGE_MERGE_CONFLICT_RESOLUTION,
    normalize_developer_phase,
)

PHASE3A_EXECUTABLE_NODES = frozenset({"implementation_plan", "development", "mr_creation"})


class OrchestrationEngine:
    """Server-side orchestrator for Work Order execution graphs."""

    def __init__(
        self,
        events: EventStore,
        *,
        agent_bridge: Any,
        gate_service: Any | None = None,
        queue_consumer: Any | None = None,
    ) -> None:
        self.events = events
        self.agent_bridge = agent_bridge
        self.gate_service = gate_service
        self.queue_consumer = queue_consumer

    def bind_gate_service(self, gate_service: Any) -> None:
        self.gate_service = gate_service

    def bind_queue_consumer(self, queue_consumer: Any) -> None:
        self.queue_consumer = queue_consumer

    def tick(self, work_order_id: str | None = None) -> list[str]:
        """Advance eligible work orders. Returns touched work order IDs."""
        touched: list[str] = []
        work_order_ids = self._work_order_ids_for_tick(work_order_id)

        for wo_id in work_order_ids:
            progressed = False
            if self._reconcile_merged_qa_validation(wo_id):
                progressed = True
            while True:
                prepared = self._prepare_node_execution(wo_id)
                if prepared is None:
                    break

                node, node_view, context = prepared
                try:
                    result = asyncio.run(
                        self.agent_bridge.run_node(wo_id, node_view, context)
                    )
                except Exception as exc:
                    self._persist_node_failure(wo_id, node, exc)
                    progressed = True
                    break

                gate_opened = self._persist_node_success(wo_id, node, context, result)
                progressed = True
                if gate_opened:
                    break

            if progressed:
                touched.append(wo_id)
        return touched

    def _work_order_ids_for_tick(self, work_order_id: str | None) -> list[str]:
        with connect() as conn:
            if work_order_id:
                return [work_order_id]
            rows = conn.execute(
                """
                SELECT id FROM work_orders
                WHERE status IN ('intake', 'running')
                ORDER BY updated_at ASC
                """
            ).fetchall()
            return [str(row["id"]) for row in rows]

    def _prepare_node_execution(
        self,
        work_order_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
        with connect() as conn:
            if has_pending_gate(conn, work_order_id):
                return None
            ready_nodes = find_ready_nodes(
                conn,
                work_order_id,
                node_types=PHASE3A_EXECUTABLE_NODES,
            )
            if not ready_nodes:
                return None

            node = ready_nodes[0]
            node_id = node["id"]
            mark_node_running(conn, node_id)
            self._set_work_order_status(
                conn,
                work_order_id,
                status="running",
                current_stage=self._stage_for_running_node(
                    node["nodeType"],
                    node_payload=node.get("payload") or {},
                ),
            )
            self.events.append(
                event_type="GRAPH_NODE_STARTED",
                work_order_id=work_order_id,
                actor="system",
                payload={"nodeId": node_id, "nodeType": node["nodeType"]},
                conn=conn,
            )
            try:
                context = self._build_agent_context(conn, work_order_id, node)
            except Exception as exc:
                # Mark the node failed in this transaction instead of crashing
                # the tick loop with a rolled-back 'running' state.
                self._handle_node_failure(conn, work_order_id, node, exc)
                self._mark_node_failed(conn, node_id, str(exc))
                return None
            node_view = {
                "id": node_id,
                "nodeType": node["nodeType"],
                "payload": node.get("payload") or {},
            }
            return node, node_view, context

    def _persist_node_failure(
        self,
        work_order_id: str,
        node: dict[str, Any],
        exc: Exception,
    ) -> None:
        with connect() as conn:
            try:
                self._handle_node_failure(conn, work_order_id, node, exc)
            except Exception:
                raise
            self._mark_node_failed(conn, node["id"], str(exc))

    def _persist_node_success(
        self,
        work_order_id: str,
        node: dict[str, Any],
        context: dict[str, Any],
        result: dict[str, Any],
    ) -> bool:
        """Persist node output and open gates. Returns True when a human gate was opened."""
        with connect() as conn:
            payload = {**node.get("payload", {}), **result}
            mark_node_completed(conn, node["id"], payload)
            self.events.append(
                event_type="GRAPH_NODE_COMPLETED",
                work_order_id=work_order_id,
                actor="agent",
                payload={"nodeId": node["id"], "nodeType": node["nodeType"]},
                conn=conn,
            )

            if node["nodeType"] == "implementation_plan":
                if result.get("needsClarification"):
                    self._open_clarification_gate(conn, work_order_id, node["id"], result)
                else:
                    self._open_analysis_plan_gate(conn, work_order_id, node["id"], result)
                return True
            if node["nodeType"] == "development":
                phase = normalize_developer_phase(payload.get("developerPhase"))
                if phase == DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION:
                    self._handle_merge_conflict_resolution_complete(
                        conn,
                        work_order_id,
                        node["id"],
                        result,
                        context,
                    )
                    return True
                self._auto_complete_merged_qa_validation(conn, work_order_id, result)
                self._open_code_review_gate(conn, work_order_id, node["id"], result, context)
                return True
            if node["nodeType"] == "mr_creation":
                self._open_jira_update_gate(conn, work_order_id, node["id"], payload)
                return True
            return False

    def _auto_complete_merged_qa_validation(
        self,
        conn,
        work_order_id: str,
        development_result: dict[str, Any],
    ) -> None:
        """Mark qa_validation complete — quality review runs inside the development pass."""
        row = conn.execute(
            """
            SELECT id, status FROM graph_nodes
            WHERE work_order_id = ? AND node_type = 'qa_validation'
            ORDER BY rowid ASC
            LIMIT 1
            """,
            (work_order_id,),
        ).fetchone()
        if not row or row["status"] == "completed":
            return

        qa_payload = {
            **development_result,
            "phase": "code_quality_review",
            "mergedWithDevelopment": True,
            "passed": True,
            "source": "developer_agent",
        }
        mark_node_completed(conn, str(row["id"]), qa_payload)
        self.events.append(
            event_type="GRAPH_NODE_COMPLETED",
            work_order_id=work_order_id,
            actor="system",
            payload={
                "nodeId": row["id"],
                "nodeType": "qa_validation",
                "mergedWithDevelopment": True,
            },
            conn=conn,
        )

    def _reconcile_merged_qa_validation(self, work_order_id: str) -> bool:
        """Unblock in-flight work orders stuck on qa_validation before the merge."""
        with connect() as conn:
            if has_pending_gate(conn, work_order_id):
                return False
            qa_row = conn.execute(
                """
                SELECT id, status FROM graph_nodes
                WHERE work_order_id = ? AND node_type = 'qa_validation'
                ORDER BY rowid ASC
                LIMIT 1
                """,
                (work_order_id,),
            ).fetchone()
            if not qa_row or qa_row["status"] in {"completed", "running"}:
                return False
            dev_row = conn.execute(
                """
                SELECT status FROM graph_nodes
                WHERE work_order_id = ? AND node_type = 'development'
                ORDER BY rowid ASC
                LIMIT 1
                """,
                (work_order_id,),
            ).fetchone()
            if not dev_row or dev_row["status"] != "completed":
                return False

            dev_payload = self._load_latest_development_payload(conn, work_order_id)
            if not dev_payload.get("patchArtifactPath") and not dev_payload.get("workspaceBaseline"):
                return False

            self._auto_complete_merged_qa_validation(conn, work_order_id, dev_payload)

            existing_gate = conn.execute(
                """
                SELECT 1 FROM gates
                WHERE work_order_id = ? AND gate_type = ? AND status = 'pending'
                LIMIT 1
                """,
                (work_order_id, CODE_REVIEW_GATE_TYPE),
            ).fetchone()
            if existing_gate:
                return True

            dev_node_id = self._development_node_id(conn, work_order_id)
            if not dev_node_id:
                return True

            context = self._build_agent_context(
                conn,
                work_order_id,
                {"nodeType": "development", "payload": dev_payload},
            )
            self._open_code_review_gate(conn, work_order_id, dev_node_id, dev_payload, context)
            return True

    def _handle_node_failure(
        self,
        conn,
        work_order_id: str,
        node: dict[str, Any],
        exc: Exception,
    ) -> None:
        if node.get("nodeType") == "mr_creation":
            # Publication failures keep the work order visible at mr_publication
            # instead of requeueing the already-approved patch to the queue.
            self._set_work_order_status(
                conn,
                work_order_id,
                status="failed",
                current_stage="mr_publication",
            )
            return
        if not self.queue_consumer:
            return
        row = conn.execute(
            "SELECT jira_key, readiness_id FROM work_orders WHERE id = ?",
            (work_order_id,),
        ).fetchone()
        if not row:
            return
        project_key = str(row["jira_key"]).split("-")[0]
        self.queue_consumer.handle_development_failure(
            project_key=project_key,
            jira_key=str(row["jira_key"]),
            readiness_id=str(row["readiness_id"]) if row["readiness_id"] else None,
            work_order_id=work_order_id,
            reason=f"{node['nodeType']} failed: {exc}",
            conn=conn,
        )

    @staticmethod
    def _mark_node_failed(conn, node_id: str, error: str) -> None:
        from delivery_runtime.persistence.db import json_dumps

        row = conn.execute(
            "SELECT payload_json FROM graph_nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        existing = json_loads(row["payload_json"], {}) if row else {}
        now = utc_now_iso()
        conn.execute(
            """
            UPDATE graph_nodes
            SET status = 'failed',
                payload_json = ?,
                completed_at = ?
            WHERE id = ?
            """,
            (json_dumps({**existing, "error": error}), now, node_id),
        )

    def _handle_merge_conflict_resolution_complete(
        self,
        conn,
        work_order_id: str,
        node_id: str,
        dev_result: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        """After merge-conflict resolution, reopen code review for human verification."""
        self._open_code_review_gate(conn, work_order_id, node_id, dev_result, context)

    def _open_code_review_gate(
        self,
        conn,
        work_order_id: str,
        node_id: str,
        dev_result: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        now = utc_now_iso()
        gate_id = next_public_id(conn, "G")
        approved_plan = context.get("approvedAnalysisPlan") or {}
        scope_contract = context.get("scopeContract") or {}
        dev_node_id = self._development_node_id(conn, work_order_id)
        risks = list(approved_plan.get("risks") or [])
        if dev_result.get("reviewerFeedbackApplied"):
            risks.append("Patch regenerated after structured reviewer feedback.")
        scope_validation = dev_result.get("scopeValidation") or {}
        if scope_validation.get("outcome") in {"SCOPE_VIOLATION", "SCOPE_VIOLATION_BLOCKED"}:
            risks.insert(0, scope_validation.get("reason") or "Patch modified files outside the Scope Contract.")
        elif scope_validation.get("outcome") == "SCOPE_EXPLOSION":
            risks.insert(0, scope_validation.get("reason") or "Patch exceeded Scope Contract size limits.")
        gate_payload = {
            "nodeId": dev_node_id or node_id,
            "qaNodeId": node_id if dev_node_id and dev_node_id != node_id else None,
            "summary": dev_result.get("summary", ""),
            "filesModified": dev_result.get("filesModified", []),
            "filesCreated": dev_result.get("filesCreated", []),
            "patchStats": dev_result.get("patchStats", {}),
            "diffPreview": dev_result.get("diffPreview", ""),
            "confidence": dev_result.get("confidence", 0),
            "risks": risks[:5],
            "implementationPlan": approved_plan.get("implementationPlan", ""),
            "likelyImpactedFiles": approved_plan.get("likelyImpactedFiles", []),
            "patchArtifactPath": dev_result.get("patchArtifactPath", ""),
            "reportArtifactPath": dev_result.get("reportArtifactPath", ""),
            "scopeContract": scope_contract,
            "scopeValidation": scope_validation,
        }
        conn.execute(
            """
            INSERT INTO gates (
                id, work_order_id, gate_type, status, payload_json, created_at
            ) VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (gate_id, work_order_id, CODE_REVIEW_GATE_TYPE, json_dumps(gate_payload), now),
        )
        self._set_work_order_status(
            conn,
            work_order_id,
            status="awaiting_gate",
            current_stage="code_review",
        )
        self.events.append(
            event_type="GATE_OPENED",
            work_order_id=work_order_id,
            actor="system",
            payload={
                "gateId": gate_id,
                "gateType": CODE_REVIEW_GATE_TYPE,
                "nodeId": node_id,
            },
            conn=conn,
        )

    def _open_jira_update_gate(
        self,
        conn,
        work_order_id: str,
        mr_node_id: str,
        publication_payload: dict[str, Any],
    ) -> None:
        """After MR publication, open the Jira update gate for human validation."""
        existing = conn.execute(
            """
            SELECT 1 FROM gates
            WHERE work_order_id = ? AND gate_type = ? AND status = 'pending'
            LIMIT 1
            """,
            (work_order_id, JIRA_UPDATE_GATE_TYPE),
        ).fetchone()
        if existing:
            return

        refresh_node_readiness(conn, work_order_id)
        wo_row = conn.execute(
            "SELECT jira_key FROM work_orders WHERE id = ?",
            (work_order_id,),
        ).fetchone()
        jira_key = str(wo_row["jira_key"] or "") if wo_row else ""
        mr_url = str(publication_payload.get("mrUrl") or "")
        mr_iid = publication_payload.get("mrIid")
        target_branch = str(publication_payload.get("targetBranch") or "")
        proposed_comment = "\n".join(
            line
            for line in (
                f"Delivery published for {jira_key}.",
                f"Merge request: {mr_url}" if mr_url else "",
                f"Target branch: {target_branch}" if target_branch else "",
            )
            if line
        )
        now = utc_now_iso()
        gate_id = next_public_id(conn, "G")
        gate_payload = {
            "nodeId": mr_node_id,
            "mrUrl": mr_url,
            "mrIid": mr_iid,
            "targetBranch": target_branch,
            "proposedComment": proposed_comment,
            "jiraKey": jira_key,
        }
        conn.execute(
            """
            INSERT INTO gates (
                id, work_order_id, gate_type, status, payload_json, created_at
            ) VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (gate_id, work_order_id, JIRA_UPDATE_GATE_TYPE, json_dumps(gate_payload), now),
        )
        self._set_work_order_status(
            conn,
            work_order_id,
            status="awaiting_gate",
            current_stage="jira_review",
        )
        self.events.append(
            event_type="GATE_OPENED",
            work_order_id=work_order_id,
            actor="system",
            payload={
                "gateId": gate_id,
                "gateType": JIRA_UPDATE_GATE_TYPE,
                "nodeId": mr_node_id,
            },
            conn=conn,
        )

    def _open_clarification_gate(
        self,
        conn,
        work_order_id: str,
        node_id: str,
        plan_result: dict[str, Any],
    ) -> None:
        now = utc_now_iso()
        gate_id = next_public_id(conn, "G")
        gate_payload = {
            "nodeId": node_id,
            "clarificationReason": plan_result.get("clarificationReason", ""),
            "contextPack": plan_result.get("contextPack", {}),
        }
        conn.execute(
            """
            INSERT INTO gates (
                id, work_order_id, gate_type, status, payload_json, created_at
            ) VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (gate_id, work_order_id, CLARIFICATION_GATE_TYPE, json_dumps(gate_payload), now),
        )
        self._set_work_order_status(
            conn,
            work_order_id,
            status="awaiting_gate",
            current_stage="clarification",
        )
        self.events.append(
            event_type="GATE_OPENED",
            work_order_id=work_order_id,
            actor="system",
            payload={
                "gateId": gate_id,
                "gateType": CLARIFICATION_GATE_TYPE,
                "nodeId": node_id,
            },
            conn=conn,
        )

    def _open_analysis_plan_gate(
        self,
        conn,
        work_order_id: str,
        node_id: str,
        plan_result: dict[str, Any],
    ) -> None:
        now = utc_now_iso()
        gate_id = next_public_id(conn, "G")
        gate_payload = {
            "nodeId": node_id,
            "ticketUnderstanding": plan_result.get("ticketUnderstanding", ""),
            "jiraContextUsed": plan_result.get("jiraContextUsed", {}),
            "targetRepo": plan_result.get("targetRepo", ""),
            "implementationPlan": plan_result.get("implementationPlan", ""),
            "likelyImpactedFiles": plan_result.get("likelyImpactedFiles", []),
            "risks": plan_result.get("risks", []),
            "confidenceLevel": plan_result.get("confidenceLevel", 0),
            "contextPack": plan_result.get("contextPack", {}),
        }
        conn.execute(
            """
            INSERT INTO gates (
                id, work_order_id, gate_type, status, payload_json, created_at
            ) VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (gate_id, work_order_id, GATE1_TYPE, json_dumps(gate_payload), now),
        )
        self._set_work_order_status(
            conn,
            work_order_id,
            status="awaiting_gate",
            current_stage="analysis_review",
        )
        self.events.append(
            event_type="GATE_OPENED",
            work_order_id=work_order_id,
            actor="system",
            payload={"gateId": gate_id, "gateType": GATE1_TYPE, "nodeId": node_id},
            conn=conn,
        )

    @staticmethod
    def _stage_for_running_node(node_type: str, *, node_payload: dict[str, Any] | None = None) -> str:
        if node_type == "implementation_plan":
            return "intake"
        if node_type == "mr_creation":
            return "mr_publication"
        if node_type == "qa_validation":
            return "qa_validation"
        if node_type == "development":
            phase = normalize_developer_phase((node_payload or {}).get("developerPhase"))
            if phase == DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION:
                return WORK_ORDER_STAGE_MERGE_CONFLICT_RESOLUTION
            return "development"
        return "development"

    @staticmethod
    def _set_work_order_status(
        conn,
        work_order_id: str,
        *,
        status: str,
        current_stage: str,
    ) -> None:
        now = utc_now_iso()
        conn.execute(
            """
            UPDATE work_orders
            SET status = ?, current_stage = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, current_stage, now, work_order_id),
        )

    def _build_agent_context(
        self,
        conn,
        work_order_id: str,
        node: dict[str, Any],
    ) -> dict[str, Any]:
        wo_row = conn.execute(
            "SELECT * FROM work_orders WHERE id = ?",
            (work_order_id,),
        ).fetchone()
        readiness_row = None
        if wo_row and wo_row["readiness_id"]:
            readiness_row = conn.execute(
                "SELECT * FROM readiness_records WHERE id = ?",
                (wo_row["readiness_id"],),
            ).fetchone()

        jira_snapshot = {}
        recommended_repos: list[str] = []
        if readiness_row:
            jira_snapshot = json_loads(readiness_row["jira_snapshot_json"], {})
            recommended_repos = json_loads(readiness_row["recommended_repos_json"], [])

        node_payload = node.get("payload") or {}
        rejection_feedback = node_payload.get("rejectionFeedback")
        context: dict[str, Any] = {
            "workOrder": {
                "id": wo_row["id"],
                "jiraKey": wo_row["jira_key"],
                "title": wo_row["title"],
                "description": wo_row["description"],
                "priority": wo_row["priority"],
            },
            "jiraSnapshot": jira_snapshot,
            "recommendedRepos": recommended_repos,
            "rejectionFeedback": rejection_feedback,
            "nodePayload": node_payload,
        }

        if node["nodeType"] == "mr_creation":
            context.update(self._load_publication_context(conn, work_order_id, node_payload))

        if node["nodeType"] in {"development", "qa_validation"}:
            context["approvedAnalysisPlan"] = self._load_approved_analysis_plan(conn, work_order_id)
            context["contextPack"] = self._load_implementation_context_pack(conn, work_order_id)
            context["reviewerFeedback"] = node_payload.get("reviewerFeedback") or []
            scope_contract = self._load_scope_contract(conn, work_order_id)
            if scope_contract:
                context["scopeContract"] = scope_contract.to_dict()

            dev_payload = self._load_latest_development_payload(conn, work_order_id)
            if dev_payload.get("workspacePath"):
                context["workspacePath"] = dev_payload["workspacePath"]
            if dev_payload.get("workspaceBaseline"):
                context["workspaceBaseline"] = dev_payload["workspaceBaseline"]

            if node["nodeType"] == "qa_validation":
                context["developerPhase"] = "code_quality_review"
                context["reuseWorkspace"] = True
            elif node["nodeType"] == "development":
                phase = normalize_developer_phase(node_payload.get("developerPhase"))
                context["developerPhase"] = phase
                if phase == DEVELOPER_PHASE_MERGE_CONFLICT_RESOLUTION:
                    context["mergeConflict"] = node_payload.get("mergeConflict") or {}
                    context["reuseWorkspace"] = True
                elif dev_payload.get("workspaceBaseline") and (
                    node_payload.get("reviewerFeedback") or node_payload.get("rejectionFeedback")
                ):
                    context["reuseWorkspace"] = True

        return context

    def _load_publication_context(
        self,
        conn,
        work_order_id: str,
        node_payload: dict[str, Any],
    ) -> dict[str, Any]:
        from delivery_runtime.mr_drafts.store import load_mr_draft
        from delivery_runtime.readiness.project_mapping import resolve_configured_integration_branch

        dev_payload = self._load_latest_development_payload(conn, work_order_id)
        wo_row = conn.execute(
            "SELECT jira_key, readiness_id FROM work_orders WHERE id = ?",
            (work_order_id,),
        ).fetchone()
        jira_key = str(wo_row["jira_key"] or "") if wo_row else ""
        project_key = jira_key.split("-")[0] if "-" in jira_key else jira_key

        delivery_branch = str(dev_payload.get("deliveryBranch") or "")
        if not delivery_branch and jira_key:
            from delivery_runtime.development.git_branch import format_delivery_branch_name

            issue_type = ""
            if wo_row and wo_row["readiness_id"]:
                readiness_row = conn.execute(
                    "SELECT jira_snapshot_json FROM readiness_records WHERE id = ?",
                    (wo_row["readiness_id"],),
                ).fetchone()
                if readiness_row:
                    snapshot = json_loads(readiness_row["jira_snapshot_json"], {})
                    issue_type = str(snapshot.get("issueType") or "")
            delivery_branch = format_delivery_branch_name(jira_key, issue_type)

        integration_branch = (
            resolve_configured_integration_branch(project_key)
            or str(dev_payload.get("mergeTargetBranch") or "")
        )

        draft_id = str(node_payload.get("draftId") or "")
        draft = load_mr_draft(draft_id) if draft_id else None
        if draft is None:
            raise RuntimeError(
                f"mr_creation node for work order {work_order_id} has no MR draft "
                f"(draftId={draft_id!r}); refusing to publish without approved content"
            )
        approved_plan_ref = dev_payload.get("approvedPlanRef") or {}
        if not isinstance(approved_plan_ref, dict):
            approved_plan_ref = {}
        target_repo = str(approved_plan_ref.get("targetRepo") or dev_payload.get("targetRepo") or "")
        if not target_repo:
            from delivery_runtime.readiness.project_mapping import load_project_mapping_entry

            entry = load_project_mapping_entry(project_key)
            target_repo = str(entry.get("default_repo") or "")
        from delivery_runtime.readiness.project_settings import load_project_vcs_provider

        return {
            "draftId": draft.id,
            "mrTitle": draft.title,
            "mrDescription": draft.description,
            "jiraKey": jira_key,
            "deliveryBranch": delivery_branch,
            "workspacePath": str(dev_payload.get("workspacePath") or ""),
            "integrationBranch": integration_branch,
            "projectKey": project_key,
            "targetRepo": target_repo,
            "approvedAnalysisPlan": approved_plan_ref,
            "vcs": load_project_vcs_provider(project_key),
        }

    @staticmethod
    def _load_latest_development_payload(conn, work_order_id: str) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT payload_json FROM graph_nodes
            WHERE work_order_id = ? AND node_type = 'development' AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT 1
            """,
            (work_order_id,),
        ).fetchone()
        if not row:
            return {}
        return json_loads(row["payload_json"], {})

    @staticmethod
    def _development_node_id(conn, work_order_id: str) -> str | None:
        row = conn.execute(
            """
            SELECT id FROM graph_nodes
            WHERE work_order_id = ? AND node_type = 'development'
            ORDER BY rowid ASC
            LIMIT 1
            """,
            (work_order_id,),
        ).fetchone()
        return str(row["id"]) if row else None

    @staticmethod
    def _load_scope_contract(conn, work_order_id: str):
        from delivery_runtime.development.scope_contract import ScopeContract
        from delivery_runtime.persistence.db import json_loads

        row = conn.execute(
            "SELECT * FROM scope_contracts WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if not row:
            return None
        return ScopeContract(
            work_order_id=str(row["work_order_id"]),
            allowed_files=json_loads(row["allowed_files_json"], []),
            allowed_directories=json_loads(row["allowed_directories_json"], []),
            forbidden_paths=json_loads(row["forbidden_paths_json"], []),
            max_files_touched=int(row["max_files_touched"]),
            max_lines_changed=int(row["max_lines_changed"]),
        )

    @staticmethod
    def _load_approved_analysis_plan(conn, work_order_id: str) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT payload_json FROM gates
            WHERE work_order_id = ? AND gate_type = ? AND status = 'approved'
            ORDER BY approved_at DESC
            LIMIT 1
            """,
            (work_order_id, GATE1_TYPE),
        ).fetchone()
        if row:
            return json_loads(row["payload_json"], {})
        return {}

    @staticmethod
    def _load_implementation_context_pack(conn, work_order_id: str) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT payload_json FROM graph_nodes
            WHERE work_order_id = ? AND node_type = 'implementation_plan' AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT 1
            """,
            (work_order_id,),
        ).fetchone()
        if not row:
            return {}
        payload = json_loads(row["payload_json"], {})
        return payload.get("contextPack") or {}
