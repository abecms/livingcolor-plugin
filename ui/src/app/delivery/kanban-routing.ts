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
      ctaLabel: GATE_CTA[columnId]
    })
  }

  const devJiraKeys = new Set<string>()
  for (const item of inbox?.activeDevelopments ?? []) {
    if (gateJiraKeys.has(item.jiraKey)) {
      continue
    }
    devJiraKeys.add(item.jiraKey)
    columns.dev.push({
      id: `dev-${item.workOrderId}`,
      jiraKey: item.jiraKey,
      title: item.title,
      workOrderId: item.workOrderId,
      currentStage: item.currentStage
    })
  }

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
    if (gateJiraKeys.has(ticket.jiraKey) || devJiraKeys.has(ticket.jiraKey) || doneJiraKeys.has(ticket.jiraKey)) {
      continue
    }
    columns.sprint.push({
      id: `sprint-${ticket.readinessId}`,
      jiraKey: ticket.jiraKey,
      title: ticket.title,
      readinessId: ticket.readinessId,
      workOrderId: ticket.workOrderId,
      estimatedDays: ticket.estimatedDays,
      priorityRank: ticket.priorityRank,
      ctaLabel: GATE_CTA.sprint
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
