import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'

import {
  decideCommentProposal,
  fetchDeliveryOverview,
  fetchPmInbox,
  fetchProjectConfig,
  fetchWorkOrder,
  findPendingAnalysisGate,
  findPendingCodeReviewGate,
  findReviewableMrDraftGate,
  promoteReadinessRecord,
  resumeWorkOrder,
  type PmInboxPayload,
  type PromoteReadinessResult,
  type VcsProvider
} from '@/lib/delivery'
import { MessageCircle, RefreshCw } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { $projectConfigRevision } from '@/store/project-config'
import { notify, notifyError } from '@/store/notifications'

import { useI18n } from '@/i18n'
import { $projectChatOpen, toggleProjectChatOpen } from '@/store/project-chat-layout'

import { DashboardGhostButton, DashboardPageHeader, DashboardPageShell } from './dashboard-ui'

import { useTeamWorkOrders } from '@/hooks/use-team-work-orders'
import { useWorkOrderLock } from '@/hooks/use-work-order-lock'
import { useProjectWorkspace } from '@/hooks/use-project-workspace'

import { ClarificationsPanel } from './clarifications-panel'
import { GateReviewPanel } from './gate-review-panel'
import { GenericGateReviewPanel } from './generic-gate-review-panel'
import { JiraBrowseProvider } from './jira-browse-context'
import { KanbanBoard } from './kanban-board'
import { buildKanbanColumns } from './kanban-routing'
import { MrDraftReviewPanel } from './mr-draft-review-panel'
import { PatchReviewPanel } from './patch-review-panel'
import { parseProjectKeyFromPath, isProjectWorkspacePath } from './project-navigation'
import { reviewRequestShortLabel } from './review-request-labels'
import { SprintHeaderStrip } from './sprint-header-strip'
import { StripeSetupBanner } from './stripe-setup-banner'
import { useDailyAnalysis } from './use-daily-analysis'
import { WorkOrderProgressPanel } from './work-order-progress-panel'
import type { DeliveryGate, WorkOrder } from './types'

function applyPromoteResultToInbox(
  inbox: PmInboxPayload | null,
  result: PromoteReadinessResult
): PmInboxPayload | null {
  if (!inbox?.selectedSprint) {
    return inbox
  }

  const { workOrder } = result
  const tickets = inbox.selectedSprint.tickets.map(ticket =>
    ticket.jiraKey === workOrder.jiraKey
      ? {
          ...ticket,
          workOrderId: workOrder.id,
          inDevelopment: true,
          currentStage: workOrder.currentStage,
          status: workOrder.status
        }
      : ticket
  )
  const activeDevelopments = [
    ...(inbox.activeDevelopments ?? []).filter(item => item.jiraKey !== workOrder.jiraKey),
    {
      workOrderId: workOrder.id,
      jiraKey: workOrder.jiraKey,
      title: workOrder.title,
      currentStage: workOrder.currentStage,
      status: workOrder.status,
      updatedAt: workOrder.updatedAt
    }
  ]

  return {
    ...inbox,
    selectedSprint: {
      ...inbox.selectedSprint,
      tickets,
      activeDevelopmentCount: activeDevelopments.length
    },
    activeDevelopments
  }
}

function genericGateReviewTitle(gateType?: string): string {
  switch (gateType) {
    case 'jira_update':
      return 'Jira update validation'
    case 'repo_clarification':
      return 'Repository clarification'
    default:
      return 'Approval review'
  }
}

function findNextPendingGate(workOrder: WorkOrder): DeliveryGate | undefined {
  return findPendingAnalysisGate(workOrder) ?? findPendingCodeReviewGate(workOrder) ?? undefined
}

async function findNextReviewGate(workOrder: WorkOrder): Promise<DeliveryGate | undefined> {
  return (
    findNextPendingGate(workOrder) ??
    (await findReviewableMrDraftGate(workOrder)) ??
    workOrder.gates?.find(item => item.status === 'pending')
  )
}

function resolveCachedWorkOrder(workOrderId: string, cache: WorkOrder[]): WorkOrder | undefined {
  const cached = cache.find(item => item.id === workOrderId)
  if (!cached) {
    return undefined
  }
  if ((cached.gates?.length ?? 0) > 0 || (cached.graphNodes?.length ?? 0) > 0) {
    return cached
  }
  return undefined
}

async function loadWorkOrder(workOrderId: string, cache: WorkOrder[]): Promise<WorkOrder> {
  try {
    return await fetchWorkOrder(workOrderId)
  } catch (error) {
    const cached = resolveCachedWorkOrder(workOrderId, cache)
    if (cached) {
      return cached
    }
    throw error
  }
}

export function ProjectDeliveryDashboardView() {
  const { t } = useI18n()
  const projectChatOpen = useStore($projectChatOpen)
  const { activeProject, activeProjectKey } = useProjectWorkspace()
  const [inbox, setInbox] = useState<PmInboxPayload | null>(null)
  const [localWorkOrders, setLocalWorkOrders] = useState<WorkOrder[]>([])
  const [vcsProvider, setVcsProvider] = useState<VcsProvider>('gitlab')
  const [actionId, setActionId] = useState<string | null>(null)
  const [clarificationsOpen, setClarificationsOpen] = useState(false)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [progressOpen, setProgressOpen] = useState(false)
  const [workOrder, setWorkOrder] = useState<WorkOrder | null>(null)
  const [gate, setGate] = useState<DeliveryGate | null>(null)
  const projectConfigRevision = useStore($projectConfigRevision)
  const location = useLocation()

  const sheetOpen = reviewOpen || progressOpen
  const lockWorkOrderId = sheetOpen ? workOrder?.id ?? null : null
  const { acquire: acquireWorkOrderLock, release: releaseWorkOrderLock, orgId: lockOrgId } =
    useWorkOrderLock(lockWorkOrderId)

  useEffect(() => {
    if (!lockWorkOrderId) {
      return
    }
    let cancelled = false
    void acquireWorkOrderLock().then(acquired => {
      if (!cancelled && !acquired && lockOrgId) {
        notifyError(new Error('Lock unavailable'), 'Another teammate is editing this work order')
      }
    })
    return () => {
      cancelled = true
      void releaseWorkOrderLock()
    }
  }, [acquireWorkOrderLock, lockOrgId, lockWorkOrderId, releaseWorkOrderLock])

  const requestSeq = useRef(0)
  const [refreshing, setRefreshing] = useState(false)

  const refreshDashboard = useCallback(async (options?: { manual?: boolean }) => {
    const manual = options?.manual ?? false
    const seq = ++requestSeq.current
    if (manual) {
      setRefreshing(true)
    }
    const projectKey = activeProjectKey ?? parseProjectKeyFromPath(location.pathname) ?? undefined
    try {
      const [inboxResult, overviewResult, configResult] = await Promise.allSettled([
        fetchPmInbox(projectKey),
        fetchDeliveryOverview(),
        fetchProjectConfig()
      ])

      if (seq !== requestSeq.current) {
        return
      }

      if (inboxResult.status === 'fulfilled') {
        setInbox(inboxResult.value)
      } else if (manual) {
        throw inboxResult.reason
      }

      if (overviewResult.status === 'fulfilled') {
        setLocalWorkOrders(overviewResult.value.workOrders.items)
      } else if (manual) {
        notifyError(overviewResult.reason, 'Could not refresh work orders')
      }

      if (configResult.status === 'fulfilled') {
        setVcsProvider(configResult.value.vcs === 'github' ? 'github' : 'gitlab')
      }

      if (manual && inboxResult.status === 'fulfilled') {
        notify({ kind: 'success', message: 'Dashboard refreshed.' })
      }
    } catch (error) {
      if (seq === requestSeq.current) {
        notifyError(error, 'Could not refresh dashboard')
      }
    } finally {
      if (manual && seq === requestSeq.current) {
        setRefreshing(false)
      }
    }
  }, [activeProjectKey, location.pathname])

  const { running: analysisRunning, run: runAnalysis } = useDailyAnalysis(refreshDashboard)

  useEffect(() => {
    if (!isProjectWorkspacePath(location.pathname)) {
      return
    }
    void refreshDashboard()
  }, [refreshDashboard, location.pathname, projectConfigRevision])

  const { workOrders: visibleWorkOrders } = useTeamWorkOrders(localWorkOrders)
  const completedWorkOrders = useMemo(
    () => visibleWorkOrders.filter(item => item.status === 'completed'),
    [visibleWorkOrders]
  )
  const columns = useMemo(
    () => buildKanbanColumns(inbox, completedWorkOrders, vcsProvider),
    [inbox, completedWorkOrders, vcsProvider]
  )

  const pendingProposals = useMemo(
    () => (inbox?.waitingForApproval ?? []).filter(item => item.kind !== 'gate' && item.proposalId),
    [inbox]
  )

  const [promotingReadinessId, setPromotingReadinessId] = useState<string | null>(null)
  const handleApproveTicket = useCallback(
    async (readinessId: string, jiraKey: string) => {
      if (promotingReadinessId) {
        return
      }
      setPromotingReadinessId(readinessId)
      try {
        const result = await promoteReadinessRecord(readinessId)
        setInbox(previous => applyPromoteResultToInbox(previous, result))
        notify({
          kind: 'success',
          message: `${jiraKey} approved for development.`
        })
        await refreshDashboard()
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error)
        if (/\b409\b/.test(detail) || /Only ready tickets can be promoted/i.test(detail)) {
          await refreshDashboard()
          notify({
            kind: 'info',
            message: `${jiraKey} is already in development.`
          })
          return
        }
        notifyError(error, `Could not approve ${jiraKey} for development`)
        await refreshDashboard()
      } finally {
        setPromotingReadinessId(null)
      }
    },
    [promotingReadinessId, refreshDashboard]
  )

  const handleProposalAction = useCallback(
    async (proposalId: string, action: 'approve' | 'reject') => {
      setActionId(proposalId)
      try {
        await decideCommentProposal(proposalId, action)
        notify({
          kind: 'success',
          message: action === 'approve' ? 'Communication proposal approved.' : 'Communication proposal rejected.'
        })
        await refreshDashboard()
      } catch (error) {
        notifyError(error, 'Could not update communication proposal')
      } finally {
        setActionId(null)
      }
    },
    [refreshDashboard]
  )

  const openReview = useCallback((nextWorkOrder: WorkOrder, nextGate: DeliveryGate) => {
    setProgressOpen(false)
    setWorkOrder(nextWorkOrder)
    setGate(nextGate)
    setReviewOpen(true)
  }, [])

  const openProgress = useCallback((nextWorkOrder: WorkOrder) => {
    setReviewOpen(false)
    setGate(null)
    setWorkOrder(nextWorkOrder)
    setProgressOpen(true)
  }, [])

  const handleReviewGate = useCallback(
    async (input: { workOrderId: string; gateId: string }) => {
      try {
        const loadedWorkOrder = await loadWorkOrder(input.workOrderId, visibleWorkOrders)
        const loadedGate = loadedWorkOrder.gates?.find(item => item.id === input.gateId)
        if (!loadedGate || loadedGate.status !== 'pending') {
          const nextGate = await findNextReviewGate(loadedWorkOrder)
          if (nextGate) {
            openReview(loadedWorkOrder, nextGate)
            return
          }
          notifyError(new Error('Gate not found'), 'This approval is no longer pending')
          await refreshDashboard()
          return
        }
        openReview(loadedWorkOrder, loadedGate)
      } catch (error) {
        notifyError(error, 'Could not open approval review')
      }
    },
    [openReview, refreshDashboard, visibleWorkOrders]
  )

  const handleReviewWorkOrder = useCallback(
    async (workOrderId: string) => {
      try {
        const loadedWorkOrder = await loadWorkOrder(workOrderId, visibleWorkOrders)
        const pendingGate = await findNextReviewGate(loadedWorkOrder)
        if (!pendingGate) {
          openProgress(loadedWorkOrder)
          return
        }
        openReview(loadedWorkOrder, pendingGate)
      } catch (error) {
        notifyError(error, 'Could not open work order review')
      }
    },
    [openProgress, openReview, visibleWorkOrders]
  )

  const handleResumeWorkOrder = useCallback(
    async (workOrderId: string) => {
      try {
        await resumeWorkOrder(workOrderId)
        const loadedWorkOrder = await loadWorkOrder(workOrderId, visibleWorkOrders)
        setWorkOrder(loadedWorkOrder)
        await refreshDashboard()
      } catch (error) {
        notifyError(error, 'Could not resume delivery')
      }
    },
    [refreshDashboard, visibleWorkOrders]
  )

  const handleDecision = useCallback(async () => {
    const workOrderId = workOrder?.id
    setReviewOpen(false)
    setWorkOrder(null)
    setGate(null)
    await refreshDashboard()
    if (!workOrderId) {
      return
    }
    try {
      const loadedWorkOrder = await loadWorkOrder(workOrderId, visibleWorkOrders)
      const nextGate = await findNextReviewGate(loadedWorkOrder)
      if (nextGate) {
        openReview(loadedWorkOrder, nextGate)
      }
    } catch (error) {
      notifyError(error, 'Could not load next approval step')
    }
  }, [openReview, refreshDashboard, visibleWorkOrders, workOrder?.id])

  const gateType = gate?.gateType ?? ''
  const isAnalysisGate = gateType === 'analysis_plan'
  const isPatchGate = gateType === 'code_review'
  const isMrGate = gateType === 'merge_request_review' || gateType === 'merge_request'
  const isGenericGate = Boolean(gateType) && !isAnalysisGate && !isPatchGate && !isMrGate

  const displayKey = activeProjectKey ?? 'Project'
  const displayName = activeProject?.projectName ?? 'Dashboard'
  const reviewRequestLabel = reviewRequestShortLabel(vcsProvider)

  return (
    <DashboardPageShell>
      <DashboardPageHeader
        actions={
          <>
            <DashboardGhostButton onClick={toggleProjectChatOpen} type="button">
              <MessageCircle className={cn('mr-2 size-4', projectChatOpen && 'text-primary')} />
              {projectChatOpen ? t.shell.projectChatClose : t.shell.projectChatOpen}
            </DashboardGhostButton>
            <DashboardGhostButton disabled={refreshing} onClick={() => void refreshDashboard({ manual: true })}>
              <RefreshCw className={cn('mr-2 size-4', refreshing && 'animate-spin')} />
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </DashboardGhostButton>
          </>
        }
        description={`Review sprint tickets, estimations, and approve development plans, patches, ${reviewRequestLabel} drafts, and Jira comments.`}
        eyebrow={`${displayKey} · ${displayName}`}
        title="Project Dashboard"
      />

      <div className="flex min-h-0 flex-1 flex-col gap-6">
        <StripeSetupBanner />
        <JiraBrowseProvider baseUrl={inbox?.jiraBrowseBaseUrl}>
          <SprintHeaderStrip
            analysisRunning={analysisRunning}
            reviewCount={
              (inbox?.needsClarification?.length ?? 0) +
              (inbox?.notReady?.length ?? 0) +
              pendingProposals.length
            }
            onOpenClarifications={() => setClarificationsOpen(true)}
            onRunAnalysis={() => void runAnalysis(inbox?.projectKey)}
            sprint={inbox?.selectedSprint ?? null}
          />
          <KanbanBoard
            columns={columns}
            onApproveTicket={(readinessId, jiraKey) => void handleApproveTicket(readinessId, jiraKey)}
            onClarifyTicket={() => setClarificationsOpen(true)}
            onOpenCard={workOrderId => void handleReviewWorkOrder(workOrderId)}
            onReviewGate={input => void handleReviewGate(input)}
            promotingReadinessId={promotingReadinessId}
            vcsProvider={vcsProvider}
          />
          <ClarificationsPanel
            actionId={actionId}
            items={inbox?.needsClarification ?? []}
            notReadyItems={inbox?.notReady ?? []}
            onOpenChange={setClarificationsOpen}
            onProposalAction={(proposalId, action) => void handleProposalAction(proposalId, action)}
            open={clarificationsOpen}
            proposals={pendingProposals}
          />
        </JiraBrowseProvider>
      </div>

      <GateReviewPanel
        gate={isAnalysisGate ? gate : null}
        onDecision={handleDecision}
        onOpenChange={setReviewOpen}
        open={reviewOpen && isAnalysisGate}
        workOrder={isAnalysisGate ? workOrder : null}
      />
      <PatchReviewPanel
        gate={isPatchGate ? gate : null}
        onDecision={handleDecision}
        onOpenChange={setReviewOpen}
        open={reviewOpen && isPatchGate}
        workOrder={isPatchGate ? workOrder : null}
      />
      <MrDraftReviewPanel
        gate={isMrGate ? gate : null}
        onDecision={handleDecision}
        onOpenChange={setReviewOpen}
        open={reviewOpen && isMrGate}
        vcsProvider={vcsProvider}
        workOrder={isMrGate ? workOrder : null}
      />
      <GenericGateReviewPanel
        gate={isGenericGate ? gate : null}
        onDecision={handleDecision}
        onOpenChange={setReviewOpen}
        open={reviewOpen && isGenericGate}
        title={genericGateReviewTitle(gate?.gateType)}
        vcsProvider={vcsProvider}
        workOrder={isGenericGate ? workOrder : null}
      />
      <WorkOrderProgressPanel
        onOpenChange={setProgressOpen}
        onResume={handleResumeWorkOrder}
        open={progressOpen}
        vcsProvider={vcsProvider}
        workOrder={workOrder}
      />
    </DashboardPageShell>
  )
}
