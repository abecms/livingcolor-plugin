import type { DeliveryGate, WorkOrder } from '@/app/delivery/types'
import { callDesktopApi } from '@/lib/desktop-api'

const DELIVERY_TIMEOUT_MS = 30_000

function profileScoped() {
  return {}
}

export interface ReadinessScanResult {
  projectKey: string
  scanned: number
  created: number
  updated: number
  skipped: number
}

export interface PromoteReadinessResult {
  readiness: import('@/app/delivery/types').ReadinessRecord
  workOrder: WorkOrder
}

export interface GateDecisionResult {
  gate: DeliveryGate
  workOrderId: string
}

export interface MrDraftDecisionResult {
  draft: import('@/app/delivery/types').MrDraftRecord
  workOrderId: string
}

export function fetchDeliveryOverview(): Promise<import('@/app/delivery/types').DeliveryOverview> {
  return callDesktopApi({
    ...profileScoped(),
    path: '/api/delivery/overview',
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export function fetchWorkOrder(workOrderId: string): Promise<WorkOrder> {
  return callDesktopApi<WorkOrder>({
    ...profileScoped(),
    path: `/api/delivery/work-orders/${encodeURIComponent(workOrderId)}`,
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export function resumeWorkOrder(workOrderId: string): Promise<{ workOrderId: string; status: string }> {
  return callDesktopApi({
    ...profileScoped(),
    path: `/api/delivery/work-orders/${encodeURIComponent(workOrderId)}/resume`,
    method: 'POST',
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export function scanReadinessQueue(projectKey: string): Promise<ReadinessScanResult> {
  return callDesktopApi<ReadinessScanResult>({
    ...profileScoped(),
    path: '/api/delivery/readiness/scan',
    method: 'POST',
    body: { projectKey },
    timeoutMs: 120_000
  })
}

export function promoteReadinessRecord(recordId: string): Promise<PromoteReadinessResult> {
  return callDesktopApi<PromoteReadinessResult>({
    ...profileScoped(),
    path: `/api/delivery/readiness/${encodeURIComponent(recordId)}/promote`,
    method: 'POST',
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export function dismissReadinessRecord(recordId: string): Promise<import('@/app/delivery/types').ReadinessRecord> {
  return callDesktopApi({
    ...profileScoped(),
    path: `/api/delivery/readiness/${encodeURIComponent(recordId)}/dismiss`,
    method: 'POST',
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export function reanalyzeReadinessRecord(recordId: string): Promise<import('@/app/delivery/types').ReadinessRecord> {
  return callDesktopApi({
    ...profileScoped(),
    path: `/api/delivery/readiness/${encodeURIComponent(recordId)}/reanalyze`,
    method: 'POST',
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export function approveDeliveryGate(gateId: string): Promise<GateDecisionResult> {
  return callDesktopApi<GateDecisionResult>({
    ...profileScoped(),
    path: `/api/delivery/gates/${encodeURIComponent(gateId)}/approve`,
    method: 'POST',
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export function rejectDeliveryGate(
  gateId: string,
  feedback: string,
  reviewerFeedback?: Array<{ type: string; message: string }>
): Promise<GateDecisionResult> {
  return callDesktopApi<GateDecisionResult>({
    ...profileScoped(),
    path: `/api/delivery/gates/${encodeURIComponent(gateId)}/reject`,
    method: 'POST',
    body: { feedback, reviewerFeedback },
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export function findPendingAnalysisGate(workOrder: WorkOrder): DeliveryGate | undefined {
  return workOrder.gates?.find(gate => gate.gateType === 'analysis_plan' && gate.status === 'pending')
}

export function findPendingCodeReviewGate(workOrder: WorkOrder): DeliveryGate | undefined {
  return workOrder.gates?.find(gate => gate.gateType === 'code_review' && gate.status === 'pending')
}

export function findPendingMrDraftGate(workOrder: WorkOrder): DeliveryGate | undefined {
  const pending = (workOrder.gates ?? []).filter(
    gate =>
      (gate.gateType === 'merge_request_review' || gate.gateType === 'merge_request') &&
      gate.status === 'pending'
  )
  if (!pending.length) {
    return undefined
  }
  return [...pending].sort((left, right) => right.createdAt.localeCompare(left.createdAt))[0]
}

export async function findReviewableMrDraftGate(workOrder: WorkOrder): Promise<DeliveryGate | undefined> {
  const pending = (workOrder.gates ?? []).filter(
    gate =>
      (gate.gateType === 'merge_request_review' || gate.gateType === 'merge_request') &&
      gate.status === 'pending'
  )
  const sorted = [...pending].sort((left, right) => right.createdAt.localeCompare(left.createdAt))
  for (const gate of sorted) {
    const draftId = String((gate.payload as { draftId?: string }).draftId ?? '').trim()
    if (!draftId) {
      continue
    }
    try {
      const draft = await fetchMrDraft(draftId)
      if (draft.status === 'awaiting_review' || draft.status === 'draft') {
        return gate
      }
    } catch {
      continue
    }
  }
  return undefined
}

export function workOrderNeedsResume(workOrder: WorkOrder): boolean {
  if (workOrder.status !== 'running') {
    return false
  }
  if (workOrder.gates?.some(gate => gate.status === 'pending')) {
    return false
  }
  return (workOrder.graphNodes ?? []).some(
    node => node.status === 'running' || node.status === 'ready'
  )
}

export function findLatestApprovedAnalysisGate(workOrder: WorkOrder): DeliveryGate | undefined {
  const approved = (workOrder.gates ?? []).filter(
    gate => gate.gateType === 'analysis_plan' && gate.status === 'approved'
  )
  if (!approved.length) {
    return undefined
  }
  return approved.sort((left, right) => right.createdAt.localeCompare(left.createdAt))[0]
}

export function fetchMrDraft(draftId: string): Promise<import('@/app/delivery/types').MrDraftRecord> {
  return callDesktopApi({
    ...profileScoped(),
    path: `/api/delivery/mr-drafts/${encodeURIComponent(draftId)}`,
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export function approveMrDraft(draftId: string): Promise<MrDraftDecisionResult> {
  return callDesktopApi<MrDraftDecisionResult>({
    ...profileScoped(),
    path: `/api/delivery/mr-drafts/${encodeURIComponent(draftId)}/approve`,
    method: 'POST',
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export function rejectMrDraft(draftId: string, feedback: string): Promise<MrDraftDecisionResult> {
  return callDesktopApi<MrDraftDecisionResult>({
    ...profileScoped(),
    path: `/api/delivery/mr-drafts/${encodeURIComponent(draftId)}/reject`,
    method: 'POST',
    body: { feedback },
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export interface PmInboxPayload {
  projectKey: string
  projectName: string
  productIdentity: string
  jiraBrowseBaseUrl?: string | null
  lastRun: {
    id: string
    projectKey: string
    startedAt: string
    completedAt?: string | null
    status: string
    jiraSynced?: number
    jiraFetched?: number
    analyzed?: number
    estimated?: number
    errorMessage?: string | null
  } | null
  recommendedNext: ExecutionQueueItem | null
  currentActiveDelivery: {
    workOrderId: string
    jiraKey: string
    title: string
    status: string
    currentStage: string
    startedAt: string
    updatedAt: string
    currentPhase: string
    estimation?: {
      complexity?: string
      estimatedDays?: number
      confidence?: number
    } | null
  } | null
  executionQueue: {
    items: ExecutionQueueItem[]
    executableCount: number
    blockedCount: number
  }
  selectedSprint: {
    sprintName: string
    capacityDays: number
    usedDays: number
    durationDays: number
    overflowRisk: boolean
    warnings: string[]
    tickets: Array<{
      readinessId: string
      jiraKey: string
      title: string
      estimatedDays: number
      priorityRank: number
      urgencyScore: number
      warnings: string[]
      workOrderId?: string
      inDevelopment?: boolean
      currentStage?: string
      status?: string
    }>
    activeDevelopmentCount?: number
  }
  needsClarification: Array<{
    record: import('@/app/delivery/types').ReadinessRecord
    detectedIssues: string[]
    proposal?: {
      id: string
      body: string
      proposalType: string
      status: string
    } | null
  }>
  waitingForApproval: Array<{
    kind: string
    gateId?: string | null
    proposalId?: string | null
    workOrderId?: string | null
    jiraKey?: string | null
    title?: string | null
    gateType?: string | null
    proposalType?: string | null
    label: string
    body?: string | null
    createdAt: string
  }>
  activeDevelopments: Array<{
    workOrderId: string
    jiraKey: string
    title: string
    currentStage: string
    status: string
    updatedAt: string
  }>
  projectMemoryHighlights: Array<{
    label: string
    value: string
    detail: string
  }>
  projectMemory: Record<string, unknown>
}

export interface ExecutionQueueItem {
  readinessId: string
  jiraKey: string
  title: string
  queueStatus: 'executable' | 'blocked' | 'not_development' | string
  priorityScore: number
  estimatedDays?: number | null
  complexity?: string | null
  confidence?: number | null
  blockers: string[]
  priorityFactors: Record<string, number>
  position: number
  recommendedNext: boolean
}

export interface TicketScopePayload {
  statusGroups: Array<'todo' | 'in_progress'>
  assignees: string[]
  includeUnassigned: boolean
  matchMode: 'all' | 'any'
}

export type VcsProvider = 'gitlab' | 'github'

export interface ProjectConfigPayload {
  projectKey: string
  projectName: string
  sprintDurationDays: number
  sprintCapacityDays: number
  sprintStartWeekday: number
  communicationLanguage: 'en' | 'fr'
  ticketScope: TicketScopePayload
  configPath: string
  vcs?: VcsProvider
  defaultRepo?: string | null
  jiraProjectKey?: string | null
  integrationBranch?: string | null
}

export interface JiraProjectOption {
  key: string
  name: string
}

export interface JiraProjectsPayload {
  items: JiraProjectOption[]
  linkedProjectKey?: string | null
}

export interface GitLabRepoOption {
  path: string
  gitlabId?: number | null
}

export interface GitLabReposPayload {
  items: GitLabRepoOption[]
  defaultRepo?: string | null
}

export interface VcsRepoOption {
  path: string
  gitlabId?: number | null
  githubId?: number | null
}

export interface VcsReposPayload {
  items: VcsRepoOption[]
  defaultRepo?: string | null
  provider: VcsProvider
}

export const DEFAULT_TICKET_SCOPE: TicketScopePayload = {
  statusGroups: ['todo'],
  assignees: [],
  includeUnassigned: true,
  matchMode: 'all'
}

export interface LocalProjectRow {
  jiraProjectKey: string
  projectName: string
}

function isNotFoundApiError(error: unknown): boolean {
  return error instanceof Error && /\b404\b/.test(error.message)
}

export async function fetchLocalProjects(): Promise<{ projects: LocalProjectRow[] }> {
  try {
    return await callDesktopApi({
      ...profileScoped(),
      path: '/api/delivery/projects',
      timeoutMs: DELIVERY_TIMEOUT_MS
    })
  } catch (error) {
    if (!isNotFoundApiError(error)) {
      throw error
    }
    const config = await fetchProjectConfig()
    return {
      projects: [
        {
          jiraProjectKey: config.projectKey.trim().toUpperCase(),
          projectName: config.projectName
        }
      ]
    }
  }
}

export async function createLocalProject(
  jiraProjectKey: string,
  projectName: string
): Promise<LocalProjectRow> {
  try {
    return await callDesktopApi({
      ...profileScoped(),
      path: '/api/delivery/projects',
      method: 'POST',
      body: { jiraProjectKey, projectName },
      timeoutMs: DELIVERY_TIMEOUT_MS
    })
  } catch (error) {
    if (!isNotFoundApiError(error)) {
      throw error
    }
    throw new Error(
      'Restart LivingColor (Cmd+Q) so the backend picks up local project support, then try again.'
    )
  }
}

export function fetchProjectConfig(): Promise<ProjectConfigPayload> {
  return callDesktopApi<ProjectConfigPayload>({
    ...profileScoped(),
    path: '/api/delivery/project-config',
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export function saveProjectConfig(body: {
  sprintDurationDays: number
  sprintCapacityDays: number
  sprintStartWeekday?: number
  communicationLanguage: 'en' | 'fr'
  ticketScope?: TicketScopePayload
  vcs?: VcsProvider
  defaultRepo?: string | null
  jiraProjectKey?: string | null
  integrationBranch?: string | null
}): Promise<ProjectConfigPayload> {
  return callDesktopApi<ProjectConfigPayload>({
    ...profileScoped(),
    path: '/api/delivery/project-config',
    method: 'PUT',
    body,
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export function fetchProjectGitlabRepos(projectKey: string): Promise<GitLabReposPayload> {
  return callDesktopApi<GitLabReposPayload>({
    ...profileScoped(),
    path: `/api/delivery/projects/${encodeURIComponent(projectKey)}/gitlab-repos`,
    timeoutMs: 120_000
  })
}

export function fetchProjectVcsRepos(projectKey: string): Promise<VcsReposPayload> {
  return callDesktopApi<VcsReposPayload>({
    ...profileScoped(),
    path: `/api/delivery/projects/${encodeURIComponent(projectKey)}/vcs-repos`,
    timeoutMs: 120_000
  })
}

export async function saveProjectDefaultRepo(defaultRepo: string | null): Promise<ProjectConfigPayload> {
  const config = await fetchProjectConfig()
  return saveProjectConfig({
    sprintDurationDays: config.sprintDurationDays,
    sprintCapacityDays: config.sprintCapacityDays,
    sprintStartWeekday: config.sprintStartWeekday,
    communicationLanguage: config.communicationLanguage === 'en' ? 'en' : 'fr',
    ticketScope: config.ticketScope,
    vcs: config.vcs,
    defaultRepo
  })
}

export async function saveProjectIntegrationBranch(
  integrationBranch: string | null
): Promise<ProjectConfigPayload> {
  const config = await fetchProjectConfig()
  return saveProjectConfig({
    sprintDurationDays: config.sprintDurationDays,
    sprintCapacityDays: config.sprintCapacityDays,
    sprintStartWeekday: config.sprintStartWeekday,
    communicationLanguage: config.communicationLanguage === 'en' ? 'en' : 'fr',
    ticketScope: config.ticketScope,
    vcs: config.vcs,
    integrationBranch
  })
}

export function fetchProjectJiraProjects(projectKey: string): Promise<JiraProjectsPayload> {
  return callDesktopApi<JiraProjectsPayload>({
    ...profileScoped(),
    path: `/api/delivery/projects/${encodeURIComponent(projectKey)}/jira-projects`,
    timeoutMs: 120_000
  })
}

export async function saveProjectJiraProjectKey(jiraProjectKey: string | null): Promise<ProjectConfigPayload> {
  const config = await fetchProjectConfig()
  return saveProjectConfig({
    sprintDurationDays: config.sprintDurationDays,
    sprintCapacityDays: config.sprintCapacityDays,
    sprintStartWeekday: config.sprintStartWeekday,
    communicationLanguage: config.communicationLanguage === 'en' ? 'en' : 'fr',
    ticketScope: config.ticketScope,
    vcs: config.vcs,
    jiraProjectKey
  })
}

export function resetProjectSprint(): Promise<PmInboxPayload['selectedSprint']> {
  return callDesktopApi({
    ...profileScoped(),
    path: '/api/delivery/sprint/reset',
    method: 'POST',
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export interface SprintReportResult {
  status: string
  reason?: string | null
  dedupKey?: string | null
  platform?: string | null
  publishedAt?: string | null
  messagePreview?: string | null
  error?: string | null
}

export function publishProjectSprintReport(force = false): Promise<SprintReportResult> {
  const query = force ? '?force=true' : ''
  return callDesktopApi({
    ...profileScoped(),
    path: `/api/delivery/sprint/report${query}`,
    method: 'POST',
    timeoutMs: 120_000
  })
}

export function fetchPmInbox(projectKey?: string): Promise<PmInboxPayload> {
  const query = projectKey ? `?project=${encodeURIComponent(projectKey)}` : ''
  return callDesktopApi({
    ...profileScoped(),
    path: `/api/delivery/pm-inbox${query}`,
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export interface DailyAnalysisStartResponse {
  status: 'started'
  projectKey: string
}

export interface DailyAnalysisResult {
  status?: string
  projectKey?: string
  scan?: {
    fetched?: number
    scanned?: number
    inScope?: number
    created?: number
    updated?: number
    skipped?: number
    skippedOutOfScope?: number
    skippedExcluded?: number
    dismissedOutOfScope?: number
  }
  qualification?: {
    analyzed?: number
    estimated?: number
  }
  selectedSprint?: PmInboxPayload['selectedSprint']
  autoStart?: Record<string, unknown> | null
}

export function runDailyAnalysis(
  projectKey?: string
): Promise<DailyAnalysisResult | DailyAnalysisStartResponse> {
  return callDesktopApi<DailyAnalysisResult | DailyAnalysisStartResponse>({
    ...profileScoped(),
    path: '/api/delivery/pm-inbox/daily-analysis/run',
    method: 'POST',
    body: projectKey ? { projectKey } : {},
    timeoutMs: 30_000
  })
}

export function decideCommentProposal(
  proposalId: string,
  action: 'approve' | 'reject' | 'edit',
  body?: string
): Promise<{ id: string; status: string }> {
  return callDesktopApi({
    ...profileScoped(),
    path: `/api/delivery/comment-proposals/${encodeURIComponent(proposalId)}/decision`,
    method: 'POST',
    body: { action, body },
    timeoutMs: DELIVERY_TIMEOUT_MS
  })
}

export interface AutomationSetupResult {
  status: string
  projectKey: string
  agentsProvisioned: string[]
  reposDiscovered: number
  defaultRepo?: string | null
  templateVersion: string
  warnings: string[]
}

export function setupProjectAutomation(projectKey: string, force = false): Promise<AutomationSetupResult> {
  const query = force ? '?force=true' : ''
  return callDesktopApi<AutomationSetupResult>({
    ...profileScoped(),
    path: `/api/delivery/projects/${encodeURIComponent(projectKey)}/setup-automation${query}`,
    method: 'POST',
    timeoutMs: 120_000
  })
}
