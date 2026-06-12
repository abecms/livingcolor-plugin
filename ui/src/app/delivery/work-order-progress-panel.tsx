import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { fetchMrDraft, fetchWorkOrder, findLatestApprovedAnalysisGate, workOrderNeedsResume } from '@/lib/delivery'
import { ExternalLink } from '@/lib/external-link'

import { dashboardPrimaryButtonProps, DASHBOARD_SHEET_BODY_CLASS, DASHBOARD_SHEET_HEADER_CLASS, StatusPill } from './dashboard-ui'
import { asAnalysisPlanPayload } from './gate-payload'
import { formatGraphNodeLabel, formatWorkOrderStage } from './stage-labels'
import type { GraphNode, MrDraftRecord, WorkOrder } from './types'

const NODE_LABELS: Record<string, string> = {
  implementation_plan: 'Analysis & plan',
  development: 'Development',
  qa_validation: 'QA validation',
  mr_creation: 'MR draft',
  jira_update: 'Jira update'
}

function nodeStatusTone(status: string): 'good' | 'neutral' | 'warning' {
  if (status === 'completed') {
    return 'good'
  }
  if (status === 'running') {
    return 'warning'
  }
  return 'neutral'
}

function formatNodeStatus(status: string): string {
  return status.replace(/_/g, ' ')
}

const MR_LINK_STAGES = new Set<string>(['mr_publication', 'jira_review', 'completed'])

function findMrDraftId(workOrder: WorkOrder): string {
  const gates = (workOrder.gates ?? []).filter(
    gate => gate.gateType === 'merge_request_review' || gate.gateType === 'merge_request'
  )
  const latest = [...gates].sort((left, right) => right.createdAt.localeCompare(left.createdAt))[0]
  return latest ? String((latest.payload as { draftId?: string }).draftId ?? '').trim() : ''
}

export function WorkOrderProgressPanel({
  onOpenChange,
  onResume,
  open,
  workOrder: initialWorkOrder
}: {
  onOpenChange: (open: boolean) => void
  onResume?: (workOrderId: string) => void | Promise<void>
  open: boolean
  workOrder: WorkOrder | null
}) {
  const [resuming, setResuming] = useState(false)
  const [workOrder, setWorkOrder] = useState<WorkOrder | null>(initialWorkOrder)
  const [mrDraft, setMrDraft] = useState<MrDraftRecord | null>(null)

  useEffect(() => {
    setWorkOrder(initialWorkOrder)
    setMrDraft(null)
  }, [initialWorkOrder])

  useEffect(() => {
    if (!open || !workOrder || !MR_LINK_STAGES.has(workOrder.currentStage)) {
      return
    }
    const draftId = findMrDraftId(workOrder)
    if (!draftId) {
      return
    }
    let cancelled = false
    void fetchMrDraft(draftId)
      .then(draft => {
        if (!cancelled) {
          setMrDraft(draft)
        }
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [open, workOrder?.id, workOrder?.currentStage])

  useEffect(() => {
    if (!open || !workOrder?.id) {
      return
    }
    const developmentNode = workOrder.graphNodes?.find(node => node.nodeType === 'development')
    const shouldPoll = workOrder.status === 'running' && developmentNode?.status === 'running'
    if (!shouldPoll) {
      return
    }

    let cancelled = false
    const poll = window.setInterval(() => {
      void fetchWorkOrder(workOrder.id)
        .then(next => {
          if (!cancelled) {
            setWorkOrder(next)
          }
        })
        .catch(() => undefined)
    }, 4000)

    return () => {
      cancelled = true
      window.clearInterval(poll)
    }
  }, [open, workOrder?.id, workOrder?.status, workOrder?.graphNodes])

  if (!workOrder) {
    return null
  }

  const approvedPlan = findLatestApprovedAnalysisGate(workOrder)
  const planPayload = approvedPlan ? asAnalysisPlanPayload(approvedPlan.payload) : null
  const nodes = [...(workOrder.graphNodes ?? [])].sort((left, right) => {
    const order = Object.keys(NODE_LABELS)
    return order.indexOf(left.nodeType) - order.indexOf(right.nodeType)
  })
  const developmentNode = nodes.find(node => node.nodeType === 'development')
  const mrCreationNode = nodes.find(node => node.nodeType === 'mr_creation')
  const mrUrlFromNode = String((mrCreationNode?.payload as { mrUrl?: string } | undefined)?.mrUrl ?? '').trim()
  const showResume = workOrderNeedsResume(workOrder) && Boolean(onResume)
  const agentRunning = developmentNode?.status === 'running'
  const publishedMrUrl = mrDraft?.mrUrl || mrUrlFromNode || undefined
  const publishedMrIid = mrDraft?.mrIid ?? (mrCreationNode?.payload as { mrIid?: number } | undefined)?.mrIid

  async function handleResume() {
    if (!onResume || resuming || !workOrder) {
      return
    }
    setResuming(true)
    try {
      await onResume(workOrder.id)
      const refreshed = await fetchWorkOrder(workOrder.id)
      setWorkOrder(refreshed)
    } finally {
      setResuming(false)
    }
  }

  return (
    <Sheet onOpenChange={onOpenChange} open={open}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl" side="right">
        <SheetHeader className={DASHBOARD_SHEET_HEADER_CLASS}>
          <SheetTitle>Delivery progress</SheetTitle>
          <SheetDescription>
            {workOrder.id} · {workOrder.jiraKey}
          </SheetDescription>
        </SheetHeader>

        <div className={DASHBOARD_SHEET_BODY_CLASS} data-testid="work-order-progress-panel">
          <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-3">
            <div className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)">Current state</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <StatusPill tone="neutral">{workOrder.status.replace(/_/g, ' ')}</StatusPill>
              <StatusPill tone="neutral">{formatWorkOrderStage(workOrder.currentStage)}</StatusPill>
            </div>
            <p className="mt-3 text-sm text-(--ui-text-secondary)">{workOrder.title}</p>
            {publishedMrUrl ? (
              <p className="mt-3 text-sm" data-testid="work-order-mr-link">
                <ExternalLink href={publishedMrUrl}>
                  Voir la MR {publishedMrIid != null ? `!${publishedMrIid} ` : ''}sur GitLab
                </ExternalLink>
              </p>
            ) : workOrder.currentStage === 'mr_publication' ? (
              <p className="mt-3 text-xs text-(--ui-text-tertiary)" data-testid="work-order-mr-publication-pending">
                Publication de la MR en cours…
              </p>
            ) : null}
            {showResume ? (
              <div className="mt-4 space-y-2">
                <p className="text-xs text-(--ui-text-tertiary)">
                  {agentRunning
                    ? 'Developer agent is running. This panel refreshes automatically.'
                    : 'The pipeline looks idle or stuck. Resume schedules the next orchestrator step.'}
                </p>
                <Button
                  data-testid="work-order-resume-button"
                  disabled={resuming || agentRunning}
                  onClick={() => void handleResume()}
                  size="sm"
                  {...dashboardPrimaryButtonProps()}
                >
                  {resuming ? 'Resuming…' : agentRunning ? 'Agent running…' : 'Resume delivery'}
                </Button>
              </div>
            ) : agentRunning ? (
              <p className="mt-4 text-xs text-(--ui-text-tertiary)">Developer agent is running…</p>
            ) : null}
          </div>

          <div className="space-y-2">
            <div className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)">Pipeline</div>
            <div className="space-y-2">
              {nodes.map(node => (
                <GraphNodeRow key={node.id} node={node} />
              ))}
            </div>
          </div>

          {planPayload ? (
            <div className="space-y-3">
              <div className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)">Approved plan</div>
              <PlanSection label="Target repository" value={planPayload.targetRepo} />
              <PlanSection label="Implementation plan" preformatted value={planPayload.implementationPlan} />
              <PlanList items={planPayload.likelyImpactedFiles} label="Likely impacted files" />
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function GraphNodeRow({ node }: { node: GraphNode }) {
  const label = formatGraphNodeLabel(node)
  return (
    <div className="flex items-center justify-between rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) px-3 py-2">
      <span className="text-sm text-foreground">{label}</span>
      <StatusPill tone={nodeStatusTone(node.status)}>{formatNodeStatus(node.status)}</StatusPill>
    </div>
  )
}

function PlanSection({
  label,
  preformatted,
  value
}: {
  label: string
  preformatted?: boolean
  value?: string
}) {
  if (!value) {
    return null
  }

  return (
    <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-3">
      <div className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)">{label}</div>
      {preformatted ? (
        <pre className="mt-2 whitespace-pre-wrap text-sm text-foreground">{value}</pre>
      ) : (
        <p className="mt-2 text-sm text-foreground">{value}</p>
      )}
    </div>
  )
}

function PlanList({ items, label }: { items?: string[]; label: string }) {
  if (!items?.length) {
    return null
  }

  return (
    <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-3">
      <div className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)">{label}</div>
      <ul className="mt-2 space-y-1 text-sm text-foreground">
        {items.map(item => (
          <li key={item}>• {item}</li>
        ))}
      </ul>
    </div>
  )
}
