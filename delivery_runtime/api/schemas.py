"""FastAPI schemas for Delivery Runtime API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReadinessRecordResponse(BaseModel):
    id: str
    jiraKey: str
    projectKey: str = ""
    title: str = ""
    readinessScore: int = 0
    readinessStatus: str
    analysisSummary: str = ""
    blockers: list[str] = Field(default_factory=list)
    recommendedRepos: list[str] = Field(default_factory=list)
    confidence: float = 0
    jiraSnapshot: dict[str, Any] = Field(default_factory=dict)
    analyzedAt: str | None = None
    lastAnalysisError: str | None = None
    lastAnalysisFailedAt: str | None = None
    promotedWorkOrderId: str | None = None
    createdAt: str
    updatedAt: str


class ReadinessListResponse(BaseModel):
    items: list[ReadinessRecordResponse]


class GraphNodeResponse(BaseModel):
    id: str
    workOrderId: str
    nodeType: str
    status: str
    dependsOn: list[str] = Field(default_factory=list)
    agentProfile: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    startedAt: str | None = None
    completedAt: str | None = None


class GateResponse(BaseModel):
    id: str
    workOrderId: str
    gateType: str
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    createdAt: str
    approvedAt: str | None = None
    approvedBy: str | None = None
    rejectionFeedback: str | None = None


class WorkOrderResponse(BaseModel):
    id: str
    jiraKey: str
    readinessId: str | None = None
    title: str = ""
    description: str = ""
    priority: str = ""
    status: str
    currentStage: str
    confidence: float = 0
    createdAt: str
    updatedAt: str
    graphNodes: list[GraphNodeResponse] = Field(default_factory=list)
    gates: list[GateResponse] = Field(default_factory=list)


class WorkOrderListResponse(BaseModel):
    items: list[WorkOrderResponse]


class WorkOrderResumeResponse(BaseModel):
    workOrderId: str
    status: str


class EventResponse(BaseModel):
    id: str
    workOrderId: str | None = None
    readinessId: str | None = None
    eventType: str
    payload: dict[str, Any] = Field(default_factory=dict)
    actor: str
    createdAt: str


class EventListResponse(BaseModel):
    items: list[EventResponse]


class DeliveryOverviewResponse(BaseModel):
    readiness: ReadinessListResponse
    workOrders: WorkOrderListResponse
    recentEvents: EventListResponse


class ReadinessScanRequest(BaseModel):
    projectKey: str


class ReadinessScanResponse(BaseModel):
    projectKey: str
    scanned: int
    created: int
    updated: int
    skipped: int


class PromoteReadinessResponse(BaseModel):
    readiness: ReadinessRecordResponse
    workOrder: WorkOrderResponse


class GateDecisionRequest(BaseModel):
    feedback: str = Field(default="", max_length=4000)
    reviewerFeedback: list[dict[str, Any]] | None = None


class GateDecisionResponse(BaseModel):
    gate: GateResponse
    workOrderId: str
    jiraEstimateWriteback: dict[str, Any] | None = None


class MrDraftResponse(BaseModel):
    id: str
    workOrderId: str
    title: str
    description: str
    ticketSummary: str
    implementationSummary: str
    filesModified: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    reviewers: list[str] = Field(default_factory=list)
    qaChecklist: dict[str, Any] = Field(default_factory=dict)
    decisionTrace: dict[str, Any] = Field(default_factory=dict)
    mrUrl: str = ""
    mrIid: int | None = None
    reviewRequestUrl: str = ""
    reviewRequestNumber: int | None = None
    reviewRequestProvider: str = "gitlab"
    status: str
    createdAt: str
    updatedAt: str


class MrDraftDecisionRequest(BaseModel):
    feedback: str = Field(default="", max_length=4000)


class MrDraftDecisionResponse(BaseModel):
    draft: MrDraftResponse
    workOrderId: str


class DailyAnalysisRunResponse(BaseModel):
    id: str
    projectKey: str
    startedAt: str
    completedAt: str | None = None
    status: str
    jiraSynced: int = 0
    analyzed: int = 0
    estimated: int = 0
    pipeline: dict[str, Any] = Field(default_factory=dict)
    errorMessage: str | None = None


class TicketEstimationResponse(BaseModel):
    id: str
    readinessId: str
    jiraKey: str
    complexity: str
    estimatedDays: float
    confidence: float
    createdAt: str
    runId: str | None = None


class JiraCommentProposalResponse(BaseModel):
    id: str
    readinessId: str | None = None
    workOrderId: str | None = None
    jiraKey: str
    proposalType: str
    status: str
    body: str
    createdAt: str
    updatedAt: str
    approvedBy: str | None = None
    publishedAt: str | None = None


class CommentProposalDecisionRequest(BaseModel):
    action: str
    body: str | None = None


class NeedsClarificationItemResponse(BaseModel):
    record: ReadinessRecordResponse
    detectedIssues: list[str] = Field(default_factory=list)
    proposal: JiraCommentProposalResponse | None = None


class ExecutionQueueItemResponse(BaseModel):
    readinessId: str
    jiraKey: str
    title: str
    queueStatus: str
    priorityScore: float = 0
    estimatedDays: float | None = None
    complexity: str | None = None
    confidence: float | None = None
    blockers: list[str] = Field(default_factory=list)
    priorityFactors: dict[str, float] = Field(default_factory=dict)
    position: int = 0
    recommendedNext: bool = False


class ExecutionQueueResponse(BaseModel):
    items: list[ExecutionQueueItemResponse] = Field(default_factory=list)
    executableCount: int = 0
    blockedCount: int = 0


class WaitingForApprovalItemResponse(BaseModel):
    kind: str
    gateId: str | None = None
    proposalId: str | None = None
    workOrderId: str | None = None
    jiraKey: str | None = None
    title: str | None = None
    gateType: str | None = None
    proposalType: str | None = None
    label: str
    body: str | None = None
    createdAt: str


class ActiveDevelopmentItemResponse(BaseModel):
    workOrderId: str
    jiraKey: str
    title: str
    currentStage: str
    status: str
    updatedAt: str


class CurrentActiveDeliveryResponse(BaseModel):
    workOrderId: str
    jiraKey: str
    title: str
    status: str
    currentStage: str
    startedAt: str
    updatedAt: str
    currentPhase: str
    estimation: dict[str, Any] | None = None


class ProjectMemoryHighlightResponse(BaseModel):
    label: str
    value: str
    detail: str


class SelectedSprintTicketResponse(BaseModel):
    readinessId: str
    jiraKey: str
    title: str
    estimatedDays: float
    priorityRank: int = 0
    urgencyScore: float = 0
    warnings: list[str] = Field(default_factory=list)
    readinessStatus: str | None = None
    lastAnalysisError: str | None = None
    lastAnalysisFailedAt: str | None = None
    workOrderId: str | None = None
    inDevelopment: bool = False
    currentStage: str | None = None
    status: str | None = None


class SelectedSprintResponse(BaseModel):
    sprintName: str
    capacityDays: float
    usedDays: float
    durationDays: int
    overflowRisk: bool = False
    warnings: list[str] = Field(default_factory=list)
    tickets: list[SelectedSprintTicketResponse] = Field(default_factory=list)
    activeDevelopmentCount: int = 0


class SprintReportResponse(BaseModel):
    status: str
    reason: str | None = None
    dedupKey: str | None = None
    platform: str | None = None
    publishedAt: str | None = None
    messagePreview: str | None = None
    error: str | None = None
    billingStatus: str | None = None
    billingWarning: str | None = None
    invoiceId: str | None = None
    invoiceUrl: str | None = None
    invoiceStatus: str | None = None
    invoiceTotalCents: int | None = None
    invoiceCurrency: str | None = None


class AnalysisDispatchItemResponse(BaseModel):
    jiraKey: str
    status: str
    backend: str | None = None
    durationMs: int | None = None
    error: str | None = None


class AnalysisDispatchResponse(BaseModel):
    backend: str = ""
    concurrency: int = 3
    success: int = 0
    cached: int = 0
    failed: int = 0
    skipped: int = 0
    forced: bool = False
    durationMs: int = 0
    items: list[AnalysisDispatchItemResponse] = Field(default_factory=list)


class PmInboxResponse(BaseModel):
    projectKey: str
    projectName: str = "Bibliothèque Numérique"
    productIdentity: str = "Autonomous Development Scheduler"
    jiraBrowseBaseUrl: str | None = None
    lastRun: DailyAnalysisRunResponse | None = None
    recommendedNext: ExecutionQueueItemResponse | None = None
    currentActiveDelivery: CurrentActiveDeliveryResponse | None = None
    executionQueue: ExecutionQueueResponse
    selectedSprint: SelectedSprintResponse
    needsClarification: list[NeedsClarificationItemResponse] = Field(default_factory=list)
    notReady: list[NeedsClarificationItemResponse] = Field(default_factory=list)
    waitingForApproval: list[WaitingForApprovalItemResponse] = Field(default_factory=list)
    activeDevelopments: list[ActiveDevelopmentItemResponse] = Field(default_factory=list)
    projectMemoryHighlights: list[ProjectMemoryHighlightResponse] = Field(default_factory=list)
    projectMemory: dict[str, Any] = Field(default_factory=dict)
    analysisDispatch: AnalysisDispatchResponse | None = None


class DailyAnalysisRunRequest(BaseModel):
    projectKey: str | None = None
    force: bool = False


class TicketScopePayload(BaseModel):
    statusGroups: list[str] = Field(default_factory=lambda: ["todo"])
    assignees: list[str] = Field(default_factory=list)
    includeUnassigned: bool = True
    matchMode: str = "all"

    @field_validator("matchMode")
    @classmethod
    def normalize_match_mode(cls, value: str) -> str:
        normalized = str(value or "all").strip().lower()
        return normalized if normalized in {"all", "any"} else "all"

    @field_validator("statusGroups")
    @classmethod
    def normalize_status_groups(cls, value: list[str]) -> list[str]:
        allowed = {"todo", "in_progress"}
        groups = [
            str(item).strip().lower().replace(" ", "_").replace("-", "_")
            for item in value
            if str(item).strip()
        ]
        normalized = [group for group in groups if group in allowed]
        return normalized or ["todo"]


class GitLabRepoPayload(BaseModel):
    path: str
    gitlab_id: int | None = Field(default=None, alias="gitlabId")


class GitLabReposResponse(BaseModel):
    items: list[GitLabRepoPayload] = Field(default_factory=list)
    default_repo: str | None = Field(default=None, alias="defaultRepo")


class VcsRepoPayload(BaseModel):
    path: str
    gitlabId: int | None = None
    githubId: int | None = None


class VcsReposResponse(BaseModel):
    items: list[VcsRepoPayload]
    defaultRepo: str | None = None
    provider: str = "gitlab"


class JiraProjectPayload(BaseModel):
    key: str
    name: str


class JiraProjectsResponse(BaseModel):
    items: list[JiraProjectPayload] = Field(default_factory=list)
    linkedProjectKey: str | None = None


class BillingConfigPayload(BaseModel):
    stripeCustomerId: str | None = None
    dailyRateCents: int | None = Field(default=None, ge=1)
    currency: str = "eur"
    invoiceMode: str = "draft"
    approvalRequired: bool = False
    maxInvoiceCents: int | None = Field(default=None, ge=1)


class ProjectConfigResponse(BaseModel):
    projectKey: str
    projectName: str
    sprintDurationDays: int
    sprintCapacityDays: float
    sprintStartWeekday: int = Field(default=1, ge=1, le=7)
    communicationLanguage: str
    ticketScope: TicketScopePayload
    configPath: str
    default_repo: str | None = Field(default=None, alias="defaultRepo")
    jira_project_key: str | None = Field(default=None, alias="jiraProjectKey")
    integration_branch: str | None = Field(default=None, alias="integrationBranch")
    vcs: str = "gitlab"


class LocalProjectResponse(BaseModel):
    jiraProjectKey: str
    projectName: str


class LocalProjectListResponse(BaseModel):
    projects: list[LocalProjectResponse] = Field(default_factory=list)


class LocalProjectCreateRequest(BaseModel):
    jiraProjectKey: str
    projectName: str


class ProjectConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_key: str | None = Field(default=None, alias="projectKey")
    sprintDurationDays: int = Field(ge=1, le=90)
    sprintCapacityDays: float = Field(ge=0.5, le=120)
    sprintStartWeekday: int | None = Field(default=None, ge=1, le=7)
    communicationLanguage: str = "fr"
    ticketScope: TicketScopePayload | None = None
    default_repo: str | None = Field(default=None, alias="defaultRepo")
    jira_project_key: str | None = Field(default=None, alias="jiraProjectKey")
    integration_branch: str | None = Field(default=None, alias="integrationBranch")
    vcs: str | None = None

    @field_validator("communicationLanguage")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        from delivery_runtime.communication.language import normalize_communication_language

        return normalize_communication_language(value)


class TicketEstimationUpdateRequest(BaseModel):
    estimatedDays: float = Field(gt=0, le=120)
    complexity: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class TicketEstimationUpdateResponse(BaseModel):
    estimationId: str
    readinessId: str
    jiraKey: str
    estimatedDays: float
    complexity: str
    confidence: float


class SprintSwapRequest(BaseModel):
    a: str
    b: str


class SprintResetRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_key: str | None = Field(default=None, alias="projectKey")


class SprintSelectionUpdateRequest(BaseModel):
    tickets: list[str] | None = None
    exclude: list[str] | None = None
    swap: SprintSwapRequest | None = None
    append: list[str] | None = None


class AutomationSetupResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str
    project_key: str = Field(alias="projectKey")
    agents_provisioned: list[str] = Field(alias="agentsProvisioned")
    repos_discovered: int = Field(alias="reposDiscovered")
    default_repo: str | None = Field(default=None, alias="defaultRepo")
    template_version: str = Field(alias="templateVersion")
    warnings: list[str] = Field(default_factory=list)


class AutomationStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_key: str = Field(alias="projectKey")
    status: str
    template_version: str = Field(alias="templateVersion")
    provisioned_at: str | None = Field(default=None, alias="provisionedAt")
    agents: list[dict[str, Any]]
