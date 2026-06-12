import { describe, expect, it } from 'vitest'

import type { PmInboxPayload } from '@/lib/delivery'

import { buildKanbanColumns, columnForGateType } from './kanban-routing'
import type { WorkOrder } from './types'

function makeInbox(overrides: Partial<PmInboxPayload> = {}): PmInboxPayload {
  return {
    projectKey: 'TVP',
    projectName: 'TV5MondePlus',
    productIdentity: 'LivingColor',
    jiraBrowseBaseUrl: null,
    lastRun: null,
    recommendedNext: null,
    currentActiveDelivery: null,
    executionQueue: { items: [], executableCount: 0, blockedCount: 0 },
    selectedSprint: {
      sprintName: 'Sprint 14',
      capacityDays: 10,
      usedDays: 6,
      durationDays: 14,
      overflowRisk: false,
      warnings: [],
      tickets: []
    },
    needsClarification: [],
    waitingForApproval: [],
    activeDevelopments: [],
    projectMemoryHighlights: [],
    ...overrides
  } as PmInboxPayload
}

function makeCompletedWorkOrder(jiraKey: string): WorkOrder {
  return {
    id: `WO-${jiraKey}`,
    jiraKey,
    title: `Done ${jiraKey}`,
    description: '',
    priority: 'medium',
    status: 'completed',
    currentStage: 'completed',
    confidence: 1,
    createdAt: '2026-06-01T00:00:00Z',
    updatedAt: '2026-06-10T00:00:00Z'
  }
}

describe('columnForGateType', () => {
  it('routes each known gate type to its column', () => {
    expect(columnForGateType('analysis_plan')).toBe('plan')
    expect(columnForGateType('code_review')).toBe('code_mr')
    expect(columnForGateType('merge_request_review')).toBe('code_mr')
    expect(columnForGateType('merge_request')).toBe('code_mr')
    expect(columnForGateType('jira_update')).toBe('jira')
  })

  it('falls back to the jira column for unknown gate types', () => {
    expect(columnForGateType('something_new')).toBe('jira')
  })
})

describe('buildKanbanColumns', () => {
  it('returns six columns in pipeline order even when empty', () => {
    const columns = buildKanbanColumns(makeInbox(), [])
    expect(columns.map(column => column.id)).toEqual(['sprint', 'plan', 'dev', 'code_mr', 'jira', 'done'])
    expect(columns.every(column => column.cards.length === 0)).toBe(true)
  })

  it('places pending gates in their pipeline column with a CTA', () => {
    const inbox = makeInbox({
      waitingForApproval: [
        {
          kind: 'gate',
          gateId: 'G-1',
          workOrderId: 'WO-1',
          jiraKey: 'TVP-1498',
          title: 'Player audio fix',
          gateType: 'analysis_plan',
          label: 'Plan review',
          proposalId: null,
          proposalType: null,
          body: null,
          createdAt: '2026-06-11T00:00:00Z'
        },
        {
          kind: 'gate',
          gateId: 'G-2',
          workOrderId: 'WO-2',
          jiraKey: 'TVP-1489',
          title: 'Guide TV rendering',
          gateType: 'jira_update',
          label: 'Jira update',
          proposalId: null,
          proposalType: null,
          body: null,
          createdAt: '2026-06-11T00:00:00Z'
        }
      ]
    })

    const columns = buildKanbanColumns(inbox, [])
    const plan = columns.find(column => column.id === 'plan')!
    const jira = columns.find(column => column.id === 'jira')!

    expect(plan.cards).toHaveLength(1)
    expect(plan.cards[0]).toMatchObject({ jiraKey: 'TVP-1498', gateId: 'G-1', ctaLabel: 'Review plan' })
    expect(jira.cards[0]).toMatchObject({ jiraKey: 'TVP-1489', gateId: 'G-2', ctaLabel: 'Validate Jira' })
  })

  it('keeps sprint tickets without work orders in the sprint column', () => {
    const inbox = makeInbox()
    inbox.selectedSprint.tickets = [
      {
        readinessId: 'R-1',
        jiraKey: 'TVP-1502',
        title: 'Pagination guide TV',
        estimatedDays: 0.5,
        priorityRank: 1,
        urgencyScore: 8.2,
        warnings: []
      }
    ]

    const columns = buildKanbanColumns(inbox, [])
    const sprint = columns.find(column => column.id === 'sprint')!
    expect(sprint.cards[0]).toMatchObject({
      jiraKey: 'TVP-1502',
      readinessId: 'R-1',
      ctaLabel: 'Approve dev'
    })
  })

  it('puts active developments without pending gate in the dev column', () => {
    const inbox = makeInbox({
      activeDevelopments: [
        {
          workOrderId: 'WO-3',
          jiraKey: 'TVP-1510',
          title: 'Cache headers',
          currentStage: 'development',
          status: 'running',
          updatedAt: '2026-06-11T00:00:00Z'
        }
      ]
    })

    const columns = buildKanbanColumns(inbox, [])
    const dev = columns.find(column => column.id === 'dev')!
    expect(dev.cards[0]).toMatchObject({ jiraKey: 'TVP-1510', workOrderId: 'WO-3' })
  })

  it('excludes from dev the tickets that already sit in a gate column', () => {
    const inbox = makeInbox({
      activeDevelopments: [
        {
          workOrderId: 'WO-2',
          jiraKey: 'TVP-1489',
          title: 'Guide TV rendering',
          currentStage: 'jira_review',
          status: 'awaiting_gate',
          updatedAt: '2026-06-11T00:00:00Z'
        }
      ],
      waitingForApproval: [
        {
          kind: 'gate',
          gateId: 'G-2',
          workOrderId: 'WO-2',
          jiraKey: 'TVP-1489',
          title: 'Guide TV rendering',
          gateType: 'jira_update',
          label: 'Jira update',
          proposalId: null,
          proposalType: null,
          body: null,
          createdAt: '2026-06-11T00:00:00Z'
        }
      ]
    })

    const columns = buildKanbanColumns(inbox, [])
    expect(columns.find(column => column.id === 'dev')!.cards).toHaveLength(0)
    expect(columns.find(column => column.id === 'jira')!.cards).toHaveLength(1)
  })

  it('fills done with completed work orders belonging to the current sprint only', () => {
    const inbox = makeInbox()
    inbox.selectedSprint.tickets = [
      {
        readinessId: 'R-9',
        jiraKey: 'TVP-1471',
        title: 'Login redirect',
        estimatedDays: 1,
        priorityRank: 2,
        urgencyScore: 5,
        warnings: []
      }
    ]

    const columns = buildKanbanColumns(inbox, [
      makeCompletedWorkOrder('TVP-1471'),
      makeCompletedWorkOrder('TVP-0001')
    ])
    const done = columns.find(column => column.id === 'done')!
    expect(done.cards.map(card => card.jiraKey)).toEqual(['TVP-1471'])
  })

  it('removes sprint-column duplicates for tickets already in development or done', () => {
    const inbox = makeInbox({
      activeDevelopments: [
        {
          workOrderId: 'WO-3',
          jiraKey: 'TVP-1510',
          title: 'Cache headers',
          currentStage: 'development',
          status: 'running',
          updatedAt: '2026-06-11T00:00:00Z'
        }
      ]
    })
    inbox.selectedSprint.tickets = [
      {
        readinessId: 'R-2',
        jiraKey: 'TVP-1510',
        title: 'Cache headers',
        estimatedDays: 1,
        priorityRank: 1,
        urgencyScore: 7,
        warnings: []
      }
    ]

    const columns = buildKanbanColumns(inbox, [])
    expect(columns.find(column => column.id === 'sprint')!.cards).toHaveLength(0)
    expect(columns.find(column => column.id === 'dev')!.cards).toHaveLength(1)
  })
})
