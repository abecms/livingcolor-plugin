import type { PmInboxPayload, VcsProvider } from '@/lib/delivery'

import { formatCodeReviewColumnTitle } from './review-request-labels'
import type { WorkOrder } from './types'

export type KanbanColumnId = 'sprint' | 'plan' | 'dev' | 'code_mr' | 'jira' | 'done'

export interface KanbanCard {
  id: string
  jiraKey: string
  title: string
  workOrderId?: string
  readinessId?: string
  gateId?: string
  gateType?: string
  estimatedDays?: number
  priorityRank?: number
  currentStage?: string
  readinessStatus?: string
  warnings?: string[]
  ctaLabel?: string
}

export interface KanbanColumn {
  id: KanbanColumnId
  title: string
  accent: 'neutral' | 'warning' | 'muted'
  cards: KanbanCard[]
}

const GATE_COLUMN: Record<string, KanbanColumnId> = {
  analysis_plan: 'plan',
  code_review: 'code_mr',
  merge_request_review: 'code_mr',
  merge_request: 'code_mr',
  jira_update: 'jira'
}

const GATE_CTA: Record<KanbanColumnId, string> = {
  sprint: 'Approve dev',
  plan: 'Review plan',
  dev: '',
  code_mr: 'Review',
  jira: 'Validate Jira',
  done: ''
}

function sprintCtaForTicket(ticket: {
  readinessStatus?: string | null
  readinessId?: string | null
}): string | undefined {
  const readinessId = ticket.readinessId?.trim()
  if (!readinessId) {
    return undefined
  }
  const status = (ticket.readinessStatus ?? 'ready').trim().toLowerCase()
  if (status === 'analysis_failed') {
    return undefined
  }
  if (status === 'ready') {
    return GATE_CTA.sprint
  }
  if (status === 'needs_clarification' || status === 'not_ready') {
    return 'Clarify'
  }
  return undefined
}

export function columnForGateType(gateType: string): KanbanColumnId {
  return GATE_COLUMN[gateType] ?? 'jira'
}

export function buildKanbanColumns(
  inbox: PmInboxPayload | null,
  completedWorkOrders: WorkOrder[],
  vcsProvider: VcsProvider = 'gitlab'
): KanbanColumn[] {
  const columns: Record<KanbanColumnId, KanbanCard[]> = {
    sprint: [],
    plan: [],
    dev: [],
    code_mr: [],
    jira: [],
    done: []
  }

  const sprintEstimates = new Map(
    (inbox?.selectedSprint?.tickets ?? [])
      .filter(ticket => ticket.estimatedDays != null)
      .map(ticket => [ticket.jiraKey, ticket.estimatedDays] as const)
  )

  const gateJiraKeys = new Set<string>()
  for (const item of inbox?.waitingForApproval ?? []) {
    if (item.kind !== 'gate' || !item.gateId || !item.workOrderId) {
      continue
    }
    const columnId = columnForGateType(item.gateType ?? '')
    const jiraKey = item.jiraKey ?? ''
    if (jiraKey) {
      gateJiraKeys.add(jiraKey)
    }
    columns[columnId].push({
      id: `gate-${item.gateId}`,
      jiraKey: jiraKey || item.label,
      title: item.title ?? item.label,
      workOrderId: item.workOrderId,
      gateId: item.gateId,
      gateType: item.gateType ?? 'unknown',
      estimatedDays: jiraKey ? sprintEstimates.get(jiraKey) : undefined,
      ctaLabel: GATE_CTA[columnId]
    })
  }

  const devJiraKeys = new Set<string>()
  const sprintKeys = new Set((inbox?.selectedSprint?.tickets ?? []).map(ticket => ticket.jiraKey))
  const doneJiraKeys = new Set<string>()
  for (const workOrder of completedWorkOrders) {
    if (workOrder.status !== 'completed' || !sprintKeys.has(workOrder.jiraKey)) {
      continue
    }
    doneJiraKeys.add(workOrder.jiraKey)
    columns.done.push({
      id: `done-${workOrder.id}`,
      jiraKey: workOrder.jiraKey,
      title: workOrder.title,
      workOrderId: workOrder.id
    })
  }

  for (const ticket of inbox?.selectedSprint?.tickets ?? []) {
    const jiraKey = ticket.jiraKey
    if (!jiraKey || gateJiraKeys.has(jiraKey) || devJiraKeys.has(jiraKey) || doneJiraKeys.has(jiraKey)) {
      continue
    }
    if (!(ticket.workOrderId || ticket.inDevelopment)) {
      continue
    }
    devJiraKeys.add(jiraKey)
    columns.dev.push({
      id: `dev-${ticket.workOrderId ?? jiraKey}`,
      jiraKey,
      title: ticket.title,
      workOrderId: ticket.workOrderId,
      currentStage: ticket.currentStage,
      estimatedDays: ticket.estimatedDays
    })
  }

  for (const item of inbox?.activeDevelopments ?? []) {
    if (gateJiraKeys.has(item.jiraKey) || devJiraKeys.has(item.jiraKey)) {
      continue
    }
    devJiraKeys.add(item.jiraKey)
    columns.dev.push({
      id: `dev-${item.workOrderId}`,
      jiraKey: item.jiraKey,
      title: item.title,
      workOrderId: item.workOrderId,
      currentStage: item.currentStage,
      estimatedDays: sprintEstimates.get(item.jiraKey)
    })
  }

  for (const ticket of inbox?.selectedSprint?.tickets ?? []) {
    if (gateJiraKeys.has(ticket.jiraKey) || devJiraKeys.has(ticket.jiraKey) || doneJiraKeys.has(ticket.jiraKey)) {
      continue
    }
    if (ticket.workOrderId || ticket.inDevelopment) {
      continue
    }
    const readinessId = ticket.readinessId?.trim()
    columns.sprint.push({
      id: `sprint-${readinessId || ticket.jiraKey}`,
      jiraKey: ticket.jiraKey,
      title: ticket.title,
      readinessId: readinessId || undefined,
      estimatedDays: ticket.estimatedDays,
      priorityRank: ticket.priorityRank,
      readinessStatus: ticket.readinessStatus,
      warnings: ticket.warnings,
      ctaLabel: sprintCtaForTicket(ticket)
    })
  }

  return [
    { id: 'sprint', title: 'Sprint', accent: 'neutral', cards: columns.sprint },
    { id: 'plan', title: 'Plan', accent: columns.plan.length ? 'warning' : 'neutral', cards: columns.plan },
    { id: 'dev', title: 'Dev', accent: 'neutral', cards: columns.dev },
    {
      id: 'code_mr',
      title: formatCodeReviewColumnTitle(vcsProvider),
      accent: columns.code_mr.length ? 'warning' : 'neutral',
      cards: columns.code_mr
    },
    { id: 'jira', title: 'Jira', accent: columns.jira.length ? 'warning' : 'neutral', cards: columns.jira },
    { id: 'done', title: 'Done', accent: 'muted', cards: columns.done }
  ]
}
