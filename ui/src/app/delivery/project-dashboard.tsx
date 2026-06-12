import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'

import {
  decideCommentProposal,
  fetchDeliveryOverview,
  fetchPmInbox,
  fetchWorkOrder,
  findPendingAnalysisGate,
  findPendingCodeReviewGate,
  findReviewableMrDraftGate,
  promoteReadinessRecord,
  resumeWorkOrder,
  type PmInboxPayload
} from '@/lib/delivery'
import { RefreshCw } from '@/lib/icons'
import { $projectConfigRevision } from '@/store/project-config'
import { notify, notifyError } from '@/store/notifications'

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
import { SprintHeaderStrip } from './sprint-header-strip'
import { useDailyAnalysis } from './use-daily-analysis'
import { WorkOrderProgressPanel } from './work-order-progress-panel'
import type { DeliveryGate, WorkOrder } from './types'

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

export function ProjectDeliveryDashboardView() {
  const { activeProject, activeProjectKey } = useProjectWorkspace()
  const [inbox, setInbox] = useState<PmInboxPayload | null>(null)
  const [localWorkOrders, setLocalWorkOrders] = useState<WorkOrder[]>([])
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
  const refreshDashboard = useCallback(async () => {
    const seq = ++requestSeq.current
    try {
      const projectKey = parseProjectKeyFromPath(location.pathname) ?? undefined
      const [payload, overview] = await Promise.all([fetchPmInbox(projectKey), fetchDeliveryOverview()])
      if (seq !== requestSeq.current) {
        return
      }
      setInbox(payload)
      setLocalWorkOrders(overview.workOrders.items)
    } catch (error) {
      if (seq === requestSeq.current) {
        notifyError(error, 'Execution queue is not ready yet')
      }
    }
  }, [location.pathname])

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
  const columns = useMemo(() => buildKanbanColumns(inbox, completedWorkOrders), [inbox, completedWorkOrders])

  const pendingProposals = useMemo(
    () => (inbox?.waitingForApproval ?? []).filter(item => item.kind !== 'gate' && item.proposalId),
    [inbox]
  )

  const promotingRef = useRef<string | null>(null)
  const handleApproveTicket = useCallback(
    async (readinessId: string, jiraKey: string) => {
      if (promotingRef.current) {
        return
      }
      promotingRef.current = readinessId
      try {
        await promoteReadinessRecord(readinessId)
        notify({
          kind: 'success',
          message: `${jiraKey} approved for development.`
        })
        await refreshDashboard()
      } catch (error) {
        notifyError(error, `Could not approve ${jiraKey} for development`)
      } finally {
        promotingRef.current = null
      }
    },
    [refreshDashboard]
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
        const loadedWorkOrder = await fetchWorkOrder(input.workOrderId)
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
    [openReview, refreshDashboard]
  )

  const handleReviewWorkOrder = useCallback(
    async (workOrderId: string) => {
      try {
        const loadedWorkOrder = await fetchWorkOrder(workOrderId)
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
    [openProgress, openReview]
  )

  const handleResumeWorkOrder = useCallback(
    async (workOrderId: string) => {
      try {
        await resumeWorkOrder(workOrderId)
        const loadedWorkOrder = await fetchWorkOrder(workOrderId)
        setWorkOrder(loadedWorkOrder)
        await refreshDashboard()
      } catch (error) {
        notifyError(error, 'Could not resume delivery')
      }
    },
    [refreshDashboard]
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
      const loadedWorkOrder = await fetchWorkOrder(workOrderId)
      const nextGate = await findNextReviewGate(loadedWorkOrder)
      if (nextGate) {
        openReview(loadedWorkOrder, nextGate)
      }
    } catch (error) {
      notifyError(error, 'Could not load next approval step')
    }
  }, [openReview, refreshDashboard, workOrder?.id])

  const gateType = gate?.gateType ?? ''
  const isAnalysisGate = gateType === 'analysis_plan'
  const isPatchGate = gateType === 'code_review'
  const isMrGate = gateType === 'merge_request_review' || gateType === 'merge_request'
  const isGenericGate = Boolean(gateType) && !isAnalysisGate && !isPatchGate && !isMrGate

  const displayKey = activeProjectKey ?? 'Project'
  const displayName = activeProject?.projectName ?? 'Dashboard'

  return (
    <DashboardPageShell>
      <DashboardPageHeader
        actions={
          <DashboardGhostButton onClick={() => void refreshDashboard()}>
            <RefreshCw className="mr-2 size-4" />
            Refresh
          </DashboardGhostButton>
        }
        description="Review sprint tickets, estimations, and approve development plans, patches, MR drafts, and Jira comments."
        eyebrow={`${displayKey} · ${displayName}`}
        title="Project Dashboard"
      />

      <div className="flex min-h-0 flex-1 flex-col gap-6">
        <JiraBrowseProvider baseUrl={inbox?.jiraBrowseBaseUrl}>
          <SprintHeaderStrip
            analysisRunning={analysisRunning}
            clarificationCount={(inbox?.needsClarification?.length ?? 0) + pendingProposals.length}
            onOpenClarifications={() => setClarificationsOpen(true)}
            onRunAnalysis={() => void runAnalysis(inbox?.projectKey)}
            sprint={inbox?.selectedSprint ?? null}
          />
          <KanbanBoard
            columns={columns}
            onApproveTicket={(readinessId, jiraKey) => void handleApproveTicket(readinessId, jiraKey)}
            onOpenCard={workOrderId => void handleReviewWorkOrder(workOrderId)}
            onReviewGate={input => void handleReviewGate(input)}
          />
          <ClarificationsPanel
            actionId={actionId}
            items={inbox?.needsClarification ?? []}
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
        workOrder={isMrGate ? workOrder : null}
      />
      <GenericGateReviewPanel
        gate={isGenericGate ? gate : null}
        onDecision={handleDecision}
        onOpenChange={setReviewOpen}
        open={reviewOpen && isGenericGate}
        title={genericGateReviewTitle(gate?.gateType)}
        workOrder={isGenericGate ? workOrder : null}
      />
      <WorkOrderProgressPanel
        onOpenChange={setProgressOpen}
        onResume={handleResumeWorkOrder}
        open={progressOpen}
        workOrder={workOrder}
      />
    </DashboardPageShell>
  )
}
