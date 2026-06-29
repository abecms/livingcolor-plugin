import { describe, expect, it } from 'vitest'

import { computeSprintUsedDays, ticketCountsTowardSprintCapacity } from './sprint-capacity'

describe('sprint-capacity', () => {
  it('counts ready backlog tickets', () => {
    const ticket = {
      readinessId: 'RD-1',
      jiraKey: 'BN-1',
      title: 'Ready',
      estimatedDays: 1.5,
      priorityRank: 1,
      urgencyScore: 1,
      warnings: [],
      readinessStatus: 'ready'
    }
    expect(ticketCountsTowardSprintCapacity(ticket)).toBe(true)
    expect(computeSprintUsedDays([ticket])).toBe(1.5)
  })

  it('keeps sprint-selected in-development tickets in the total', () => {
    const ticket = {
      readinessId: 'RD-1',
      jiraKey: 'BN-1',
      title: 'Approved',
      estimatedDays: 2,
      priorityRank: 1,
      urgencyScore: 1,
      warnings: [],
      readinessStatus: 'ready',
      sprintSelected: true,
      inDevelopment: true,
      workOrderId: 'WO-1'
    }
    expect(ticketCountsTowardSprintCapacity(ticket)).toBe(true)
    expect(computeSprintUsedDays([ticket])).toBe(2)
  })

  it('excludes carry-over in-development tickets', () => {
    const ticket = {
      readinessId: 'RD-9',
      jiraKey: 'BN-9',
      title: 'Carry over',
      estimatedDays: 1,
      priorityRank: 9,
      urgencyScore: 0,
      warnings: [],
      sprintSelected: false,
      inDevelopment: true,
      workOrderId: 'WO-9'
    }
    expect(ticketCountsTowardSprintCapacity(ticket)).toBe(false)
    expect(computeSprintUsedDays([ticket])).toBe(0)
  })
})
