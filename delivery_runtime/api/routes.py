"""Delivery Runtime HTTP API."""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from delivery_runtime.api.deps import get_services
from delivery_runtime.api.schemas import (
    AutomationSetupResponse,
    AutomationStatusResponse,
    CommentProposalDecisionRequest,
    DeliveryOverviewResponse,
    EventListResponse,
    GateDecisionRequest,
    GateDecisionResponse,
    GateResponse,
    GitLabRepoPayload,
    GitLabReposResponse,
    JiraProjectPayload,
    JiraProjectsResponse,
    JiraCommentProposalResponse,
    MrDraftDecisionRequest,
    MrDraftDecisionResponse,
    MrDraftResponse,
    PmInboxResponse,
    LocalProjectCreateRequest,
    LocalProjectListResponse,
    LocalProjectResponse,
    ProjectConfigResponse,
    ProjectConfigUpdateRequest,
    PromoteReadinessResponse,
    SelectedSprintResponse,
    SprintSelectionUpdateRequest,
    TicketEstimationUpdateRequest,
    TicketEstimationUpdateResponse,
    ReadinessListResponse,
    ReadinessRecordResponse,
    ReadinessScanRequest,
    ReadinessScanResponse,
    DailyAnalysisRunRequest,
    WorkOrderListResponse,
    WorkOrderResponse,
    WorkOrderResumeResponse,
)
from delivery_runtime.readiness.errors import ReadinessIntegrationError

router = APIRouter(tags=["delivery"])


def _delivery_db_unavailable_detail(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if "locked" in message.lower():
        return (
            "Delivery database is locked by another LivingColor process. "
            "Stop shadow evaluation or other delivery scripts, then retry."
        )
    return f"Delivery database is unavailable: {message}"


@router.get("/overview", response_model=DeliveryOverviewResponse)
def get_delivery_overview() -> DeliveryOverviewResponse:
    """Mission Control bootstrap payload."""
    from delivery_runtime.api.schemas import EventResponse

    services = get_services()
    try:
        readiness_items = [
            ReadinessRecordResponse.model_validate(item)
            for item in services.readiness.list_records()
        ]
        work_order_items = [
            WorkOrderResponse.model_validate(item)
            for item in services.work_orders.list_work_orders()
        ]
        event_items = [
            EventResponse.model_validate(item) for item in services.events.list_recent()
        ]
    except sqlite3.OperationalError as exc:
        raise HTTPException(status_code=503, detail=_delivery_db_unavailable_detail(exc)) from exc
    return DeliveryOverviewResponse(
        readiness=ReadinessListResponse(items=readiness_items),
        workOrders=WorkOrderListResponse(items=work_order_items),
        recentEvents=EventListResponse(items=event_items),
    )


@router.get("/readiness", response_model=ReadinessListResponse)
def list_readiness(status: str | None = None, project: str | None = None) -> ReadinessListResponse:
    services = get_services()
    items = [
        ReadinessRecordResponse.model_validate(item)
        for item in services.readiness.list_records(status=status, project_key=project)
    ]
    return ReadinessListResponse(items=items)


@router.post("/readiness/scan", response_model=ReadinessScanResponse)
async def scan_readiness(body: ReadinessScanRequest) -> ReadinessScanResponse:
    project_key = body.projectKey.strip().upper()
    if not project_key:
        raise HTTPException(status_code=400, detail="projectKey is required")
    services = get_services()
    try:
        result = await asyncio.to_thread(services.readiness.scan_project, project_key)
    except ReadinessIntegrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReadinessScanResponse.model_validate(result)


@router.get("/readiness/{record_id}", response_model=ReadinessRecordResponse)
def get_readiness(record_id: str) -> ReadinessRecordResponse:
    services = get_services()
    record = services.readiness.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Readiness record not found")
    return ReadinessRecordResponse.model_validate(record)


@router.post("/readiness/{record_id}/promote", response_model=PromoteReadinessResponse)
def promote_readiness(record_id: str) -> PromoteReadinessResponse:
    services = get_services()
    try:
        work_order = services.readiness.promote(record_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    readiness = services.readiness.get_record(record_id)
    if not readiness:
        readiness = {
            "id": record_id,
            "jiraKey": work_order["jiraKey"],
            "projectKey": "",
            "title": work_order["title"],
            "readinessScore": 0,
            "readinessStatus": "promoted",
            "analysisSummary": "",
            "blockers": [],
            "recommendedRepos": [],
            "confidence": work_order.get("confidence", 0),
            "promotedWorkOrderId": work_order["id"],
            "createdAt": work_order["createdAt"],
            "updatedAt": work_order["updatedAt"],
        }
    return PromoteReadinessResponse(
        readiness=ReadinessRecordResponse.model_validate(readiness),
        workOrder=WorkOrderResponse.model_validate(work_order),
    )


@router.post("/readiness/{record_id}/dismiss", response_model=ReadinessRecordResponse)
def dismiss_readiness(record_id: str) -> ReadinessRecordResponse:
    services = get_services()
    try:
        record = services.readiness.dismiss(record_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ReadinessRecordResponse.model_validate(record)


@router.post("/readiness/{record_id}/reanalyze", response_model=ReadinessRecordResponse)
def reanalyze_readiness(record_id: str) -> ReadinessRecordResponse:
    services = get_services()
    try:
        record = services.readiness.reanalyze(record_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ReadinessRecordResponse.model_validate(record)


@router.get("/work-orders", response_model=WorkOrderListResponse)
def list_work_orders(stage: str | None = None, status: str | None = None) -> WorkOrderListResponse:
    services = get_services()
    items = [
        WorkOrderResponse.model_validate(item)
        for item in services.work_orders.list_work_orders(stage=stage, status=status)
    ]
    return WorkOrderListResponse(items=items)


@router.get("/work-orders/{work_order_id}", response_model=WorkOrderResponse)
def get_work_order(work_order_id: str) -> WorkOrderResponse:
    services = get_services()
    record = services.work_orders.get_work_order(work_order_id)
    if not record:
        raise HTTPException(status_code=404, detail="Work order not found")
    return WorkOrderResponse.model_validate(record)


@router.post("/work-orders/{work_order_id}/resume", response_model=WorkOrderResumeResponse)
def resume_work_order(work_order_id: str) -> WorkOrderResumeResponse:
    from delivery_runtime.orchestration.background import schedule_orchestrator_tick
    from delivery_runtime.orchestration.resume import prepare_work_order_resume
    from delivery_runtime.persistence.db import connect

    services = get_services()
    if not services.work_orders.get_work_order(work_order_id):
        raise HTTPException(status_code=404, detail="Work order not found")
    with connect() as conn:
        prepare_work_order_resume(conn, work_order_id)
    schedule_orchestrator_tick(services.orchestrator, work_order_id)
    return WorkOrderResumeResponse(workOrderId=work_order_id, status="scheduled")


@router.get("/work-orders/{work_order_id}/events", response_model=EventListResponse)
def list_work_order_events(work_order_id: str, limit: int = 100) -> EventListResponse:
    from delivery_runtime.api.schemas import EventResponse

    services = get_services()
    if not services.work_orders.get_work_order(work_order_id):
        raise HTTPException(status_code=404, detail="Work order not found")
    items = [
        EventResponse.model_validate(item)
        for item in services.events.list_for_work_order(work_order_id, limit=limit)
    ]
    return EventListResponse(items=items)


@router.get("/gates/{gate_id}", response_model=GateResponse)
def get_gate(gate_id: str) -> GateResponse:
    gate = get_services().gates.get_gate(gate_id)
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")
    return GateResponse.model_validate(gate)


@router.post("/gates/{gate_id}/approve", response_model=GateDecisionResponse)
def approve_gate(gate_id: str) -> GateDecisionResponse:
    services = get_services()
    try:
        result = services.gates.approve(gate_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return GateDecisionResponse.model_validate(result)


@router.post("/gates/{gate_id}/reject", response_model=GateDecisionResponse)
def reject_gate(gate_id: str, body: GateDecisionRequest | None = None) -> GateDecisionResponse:
    services = get_services()
    feedback = body.feedback if body else ""
    structured = body.reviewerFeedback if body else None
    try:
        result = services.gates.reject(
            gate_id,
            feedback=feedback,
            structured_feedback=structured,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GateDecisionResponse.model_validate(result)


@router.get("/mr-drafts/{draft_id}", response_model=MrDraftResponse)
def get_mr_draft(draft_id: str) -> MrDraftResponse:
    services = get_services()
    draft = services.mr_drafts.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="MR draft not found")
    return MrDraftResponse.model_validate(draft.to_dict())


@router.post("/mr-drafts/{draft_id}/approve", response_model=MrDraftDecisionResponse)
def approve_mr_draft(draft_id: str) -> MrDraftDecisionResponse:
    services = get_services()
    try:
        draft = services.mr_drafts.approve_draft(draft_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return MrDraftDecisionResponse(
        draft=MrDraftResponse.model_validate(draft.to_dict()),
        workOrderId=draft.work_order_id,
    )


@router.post("/mr-drafts/{draft_id}/reject", response_model=MrDraftDecisionResponse)
def reject_mr_draft(draft_id: str, body: MrDraftDecisionRequest | None = None) -> MrDraftDecisionResponse:
    services = get_services()
    feedback = body.feedback if body else ""
    try:
        draft = services.mr_drafts.reject_draft(draft_id, feedback=feedback)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MrDraftDecisionResponse(
        draft=MrDraftResponse.model_validate(draft.to_dict()),
        workOrderId=draft.work_order_id,
    )


@router.get("/events", response_model=EventListResponse)
def list_recent_events(limit: int = 50) -> EventListResponse:
    from delivery_runtime.api.schemas import EventResponse

    services = get_services()
    items = [EventResponse.model_validate(item) for item in services.events.list_recent(limit=limit)]
    return EventListResponse(items=items)


def _request_project_key(request: Request | None = None) -> str | None:
    from delivery_runtime.automation.project_context import resolve_request_project_key

    return resolve_request_project_key(request)


def _activate_local_project_from_request(request: Request | None = None) -> str | None:
    from delivery_runtime.automation.project_context import resolve_request_project_key, try_activate_local_project

    project_key = resolve_request_project_key(request)
    try_activate_local_project(project_key)
    return project_key


def _project_name_for_key(project_key: str, fallback: str) -> str:
    from delivery_runtime.readiness.project_mapping import load_project_mapping

    mapping = load_project_mapping()
    if isinstance(mapping, dict):
        block = mapping.get(project_key) or mapping.get(project_key.lower()) or {}
        if isinstance(block, dict):
            name = str(block.get("name") or block.get("project_name") or "").strip()
            if name:
                return name
    return fallback


def _ticket_scope_response(project_key: str) -> "TicketScopePayload":
    from delivery_runtime.api.schemas import TicketScopePayload
    from delivery_runtime.readiness.ticket_scope import load_ticket_scope_for_project, serialize_ticket_scope

    scope = load_ticket_scope_for_project(project_key)
    return TicketScopePayload.model_validate(serialize_ticket_scope(scope))


def _project_config_response(project_key: str, project_name: str, config) -> ProjectConfigResponse:
    from delivery_runtime.automation.config import delivery_config_path
    from delivery_runtime.readiness.project_settings import (
        load_project_default_repo,
        load_project_integration_branch,
        resolve_jira_project_key,
    )

    return ProjectConfigResponse(
        projectKey=project_key,
        projectName=project_name,
        sprintDurationDays=config.sprint.duration_days,
        sprintCapacityDays=config.sprint.capacity_days,
        communicationLanguage=config.communication_language,
        ticketScope=_ticket_scope_response(project_key),
        configPath=str(delivery_config_path()),
        defaultRepo=load_project_default_repo(project_key),
        jiraProjectKey=resolve_jira_project_key(project_key),
        integrationBranch=load_project_integration_branch(project_key),
    )


@router.get("/project-config", response_model=ProjectConfigResponse)
def get_project_config(request: Request) -> ProjectConfigResponse:
    from delivery_runtime.automation.config import load_delivery_automation_config

    request_key = _activate_local_project_from_request(request)
    config = load_delivery_automation_config(project_key=request_key)
    project_key = request_key or config.project_key
    project_name = _project_name_for_key(project_key, config.project_name)
    return _project_config_response(project_key, project_name, config)


@router.get("/projects", response_model=LocalProjectListResponse)
def list_local_delivery_projects() -> LocalProjectListResponse:
    from delivery_runtime.automation.local_projects import list_local_projects

    rows = list_local_projects()
    return LocalProjectListResponse(
        projects=[LocalProjectResponse.model_validate(row) for row in rows],
    )


@router.get("/projects/{project_key}/gitlab-repos", response_model=GitLabReposResponse)
def list_project_gitlab_repos(project_key: str) -> GitLabReposResponse:
    from delivery_runtime.readiness.project_settings import (
        load_project_default_repo,
        load_project_gitlab_repos,
        resolve_project_mcp_server,
    )
    from lc_server.provisioning.gitlab_discovery import discover_gitlab_repos_for_project

    key = project_key.strip().upper()
    gitlab_config = resolve_project_mcp_server(key, "gitlab")
    if not gitlab_config:
        raise HTTPException(status_code=400, detail={"error": "gitlab_mcp_not_configured"})

    cached = load_project_gitlab_repos(key)
    discovery = None
    try:
        discovery = discover_gitlab_repos_for_project(key, gitlab_config)
        repos = discovery.repos or cached
    except Exception as exc:
        if cached:
            repos = cached
        else:
            raise HTTPException(status_code=502, detail=f"GitLab repository listing failed: {exc}") from exc

    saved_default = load_project_default_repo(key)
    default_repo = saved_default or (discovery.default_repo if discovery is not None else None)

    return GitLabReposResponse(
        items=[GitLabRepoPayload.model_validate(item) for item in repos],
        defaultRepo=default_repo,
    )


@router.get("/projects/{project_key}/jira-projects", response_model=JiraProjectsResponse)
def list_project_jira_projects(project_key: str) -> JiraProjectsResponse:
    from delivery_runtime.readiness.errors import ReadinessIntegrationError
    from delivery_runtime.readiness.project_settings import resolve_jira_project_key, resolve_project_mcp_server
    from lc_server.integrations.jira_readiness import list_jira_projects_for_readiness

    key = project_key.strip().upper()
    jira_config = resolve_project_mcp_server(key, "jira")
    if not jira_config:
        raise HTTPException(status_code=400, detail={"error": "jira_mcp_not_configured"})

    try:
        projects = list_jira_projects_for_readiness(key)
    except ReadinessIntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return JiraProjectsResponse(
        items=[JiraProjectPayload.model_validate(item) for item in projects],
        linkedProjectKey=resolve_jira_project_key(key),
    )


@router.post("/projects/{project_key}/setup-automation", response_model=AutomationSetupResponse)
def setup_project_automation(project_key: str, force: bool = False) -> AutomationSetupResponse:
    from lc_server.provisioning.errors import ProvisionError
    from lc_server.provisioning.provisioner import ProjectAutomationProvisioner

    key = project_key.strip().upper()
    try:
        result = ProjectAutomationProvisioner().provision(key, force=force)
    except ProvisionError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "prerequisites_missing", "missing": exc.missing},
        ) from exc
    return AutomationSetupResponse(
        status=result.status,
        projectKey=result.project_key,
        agentsProvisioned=result.agents_provisioned,
        reposDiscovered=result.repos_discovered,
        defaultRepo=result.default_repo,
        templateVersion=result.template_version,
        warnings=result.warnings,
    )


@router.get("/projects/{project_key}/automation", response_model=AutomationStatusResponse)
def get_project_automation(project_key: str) -> AutomationStatusResponse:
    from delivery_runtime.agents.registry import AgentManifestRegistry

    registry = AgentManifestRegistry()
    state = registry.load_automation_state(project_key.strip().upper())
    if state is None:
        raise HTTPException(status_code=404, detail="Automation not provisioned")
    agents = []
    for role in ("orchestrator", "analyst", "planner", "developer", "publisher"):
        manifest = registry.get(state.project_key, role)
        if manifest:
            agents.append(
                {
                    "role": role,
                    "templateVersion": manifest.template_version,
                    "runtimeType": manifest.runtime.type,
                }
            )
    return AutomationStatusResponse(
        projectKey=state.project_key,
        status=state.status,
        templateVersion=state.template_version,
        provisionedAt=state.provisioned_at,
        agents=agents,
    )


@router.post("/projects", response_model=LocalProjectResponse)
def create_local_delivery_project(body: LocalProjectCreateRequest) -> LocalProjectResponse:
    from delivery_runtime.automation.local_projects import register_local_project

    try:
        row = register_local_project(body.jiraProjectKey, body.projectName)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LocalProjectResponse.model_validate(row)


@router.put("/project-config", response_model=ProjectConfigResponse)
def update_project_config(body: ProjectConfigUpdateRequest, request: Request) -> ProjectConfigResponse:
    from delivery_runtime.automation.config import load_delivery_automation_config, save_delivery_project_config
    from delivery_runtime.readiness.project_settings import (
        persist_project_default_repo,
        persist_project_integration_branch,
        persist_project_jira_project_key,
    )
    from delivery_runtime.readiness.ticket_scope import parse_ticket_scope

    request_key = _activate_local_project_from_request(request)
    ticket_scope = parse_ticket_scope(body.ticketScope.model_dump()) if body.ticketScope is not None else None
    save_delivery_project_config(
        capacity_days=body.sprintCapacityDays,
        duration_days=body.sprintDurationDays,
        communication_language=body.communicationLanguage,
        ticket_scope=ticket_scope,
        project_key=request_key,
    )
    target_key = request_key or load_delivery_automation_config(project_key=request_key).project_key
    if body.default_repo is not None:
        repo = body.default_repo.strip()
        if repo:
            persist_project_default_repo(target_key, repo)
    if body.jira_project_key is not None:
        linked = body.jira_project_key.strip()
        if linked:
            persist_project_jira_project_key(target_key, linked)
    if body.integration_branch is not None:
        branch = body.integration_branch.strip()
        if branch:
            persist_project_integration_branch(target_key, branch)
    config = load_delivery_automation_config(project_key=request_key)
    project_key = request_key or config.project_key
    project_name = _project_name_for_key(project_key, config.project_name)
    return _project_config_response(project_key, project_name, config)


@router.patch("/tickets/{jira_key}/estimation", response_model=TicketEstimationUpdateResponse)
def update_ticket_estimation(
    jira_key: str,
    body: TicketEstimationUpdateRequest,
    request: Request,
) -> TicketEstimationUpdateResponse:
    project_key = _activate_local_project_from_request(request)
    if not project_key:
        raise HTTPException(status_code=400, detail="Active project key is required")
    services = get_services()
    try:
        result = services.pm_inbox.update_ticket_estimation(
            project_key=project_key,
            jira_key=jira_key,
            estimated_days=body.estimatedDays,
            complexity=body.complexity,
            confidence=body.confidence,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TicketEstimationUpdateResponse.model_validate(result)


@router.put("/sprint/selection", response_model=SelectedSprintResponse)
def update_sprint_selection(
    body: SprintSelectionUpdateRequest,
    request: Request,
) -> SelectedSprintResponse:
    project_key = _activate_local_project_from_request(request)
    if not project_key:
        raise HTTPException(status_code=400, detail="Active project key is required")
    services = get_services()
    swap_payload = body.swap.model_dump() if body.swap else None
    try:
        payload = services.pm_inbox.update_sprint_selection(
            project_key=project_key,
            tickets=body.tickets,
            exclude=body.exclude,
            swap=swap_payload,
            append=body.append,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SelectedSprintResponse.model_validate(payload)


@router.get("/pm-inbox", response_model=PmInboxResponse)
def get_pm_inbox(project: str | None = None) -> PmInboxResponse:
    services = get_services()
    try:
        payload = services.pm_inbox.get_inbox(project)
    except sqlite3.OperationalError as exc:
        raise HTTPException(status_code=503, detail=_delivery_db_unavailable_detail(exc)) from exc
    return PmInboxResponse.model_validate(payload)


@router.post("/pm-inbox/daily-analysis/run")
async def run_daily_analysis(body: DailyAnalysisRunRequest | None = None) -> dict[str, Any]:
    services = get_services()
    project_key = body.projectKey.strip().upper() if body and body.projectKey else None
    try:
        result = await asyncio.to_thread(services.pm_inbox.run_daily_analysis, project_key)
    except ReadinessIntegrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.get("/projects/{jira_project_key}/share-payload")
def get_local_project_share_payload(jira_project_key: str) -> dict[str, Any]:
    from lc_server.integrations.local_project_share import build_local_project_share_payload

    try:
        return build_local_project_share_payload(jira_project_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{jira_project_key}/finalize-share")
def finalize_local_project_share(jira_project_key: str) -> dict[str, str | bool]:
    from delivery_runtime.automation.local_projects import remove_local_project

    try:
        remove_local_project(jira_project_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"jiraProjectKey": jira_project_key.strip().upper(), "removed": True}


@router.get("/cloud/pending-events")
def list_cloud_pending_events(orgId: str) -> dict[str, Any]:
    from delivery_runtime.persistence.pending_events import list_pending_events

    return {"orgId": orgId, "events": list_pending_events(orgId)}


@router.post("/cloud/pending-events")
def enqueue_cloud_pending_event(body: dict[str, Any]) -> dict[str, Any]:
    from delivery_runtime.persistence.pending_events import enqueue_pending_event

    org_id = str(body.get("orgId") or "").strip()
    wo_id = str(body.get("woId") or "").strip()
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    try:
        event_id = enqueue_pending_event(org_id, wo_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": event_id, "orgId": org_id, "woId": wo_id}


@router.post("/cloud/pending-events/mark-flushed")
def mark_cloud_pending_events_flushed(body: dict[str, Any]) -> dict[str, Any]:
    from delivery_runtime.persistence.pending_events import mark_pending_events_flushed

    raw_ids = body.get("ids") if isinstance(body.get("ids"), list) else []
    try:
        ids = [int(item) for item in raw_ids]
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="ids must be integers") from exc
    flushed = mark_pending_events_flushed(ids)
    return {"flushed": flushed}


@router.post("/comment-proposals/{proposal_id}/decision", response_model=JiraCommentProposalResponse)
def decide_comment_proposal(
    proposal_id: str,
    body: CommentProposalDecisionRequest,
) -> JiraCommentProposalResponse:
    services = get_services()
    try:
        proposal = services.pm_inbox.decide_comment_proposal(
            proposal_id,
            action=body.action,
            body=body.body,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JiraCommentProposalResponse.model_validate(proposal)
