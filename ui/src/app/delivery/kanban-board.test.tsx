import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { JiraBrowseProvider } from './jira-browse-context'
import { KanbanBoard } from './kanban-board'
import type { KanbanColumn } from './kanban-routing'

vi.mock('./use-jira-base-url', () => ({
  useJiraBaseUrl: () => null
}))

afterEach(() => {
  cleanup()
})

const columns: KanbanColumn[] = [
  {
    id: 'sprint',
    title: 'Sprint',
    accent: 'neutral',
    cards: [
      {
        id: 'sprint-R-1',
        jiraKey: 'TVP-1502',
        title: 'Pagination guide TV',
        readinessId: 'R-1',
        estimatedDays: 0.5,
        priorityRank: 1,
        ctaLabel: 'Approve dev'
      }
    ]
  },
  { id: 'plan', title: 'Plan', accent: 'neutral', cards: [] },
  {
    id: 'dev',
    title: 'Dev',
    accent: 'neutral',
    cards: [
      {
        id: 'dev-WO-3',
        jiraKey: 'TVP-1510',
        title: 'Cache headers',
        workOrderId: 'WO-3',
        currentStage: 'development'
      }
    ]
  },
  { id: 'code_mr', title: 'Code/MR', accent: 'neutral', cards: [] },
  {
    id: 'jira',
    title: 'Jira',
    accent: 'warning',
    cards: [
      {
        id: 'gate-G-2',
        jiraKey: 'TVP-1489',
        title: 'Guide TV rendering',
        workOrderId: 'WO-2',
        gateId: 'G-2',
        gateType: 'jira_update',
        ctaLabel: 'Validate Jira'
      }
    ]
  },
  { id: 'done', title: 'Done', accent: 'muted', cards: [] }
]

describe('KanbanBoard', () => {
  it('renders all six column titles with counts', () => {
    render(
      <KanbanBoard
        columns={columns}
        onApproveTicket={() => {}}
        onOpenCard={() => {}}
        onReviewGate={() => {}}
      />
    )
    expect(screen.getByTestId('kanban-board')).toBeTruthy()
    expect(screen.getByText('Sprint · 1')).toBeTruthy()
    expect(screen.getByText('Plan · 0')).toBeTruthy()
    expect(screen.getByText('Jira · 1')).toBeTruthy()
  })

  it('fires onReviewGate when the gate CTA is clicked', () => {
    const onReviewGate = vi.fn()
    render(
      <KanbanBoard
        columns={columns}
        onApproveTicket={() => {}}
        onOpenCard={() => {}}
        onReviewGate={onReviewGate}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Validate Jira' }))
    expect(onReviewGate).toHaveBeenCalledWith({ workOrderId: 'WO-2', gateId: 'G-2', gateType: 'jira_update' })
  })

  it('fires onApproveTicket when the sprint CTA is clicked', () => {
    const onApproveTicket = vi.fn()
    render(
      <KanbanBoard
        columns={columns}
        onApproveTicket={onApproveTicket}
        onOpenCard={() => {}}
        onReviewGate={() => {}}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Approve dev' }))
    expect(onApproveTicket).toHaveBeenCalledWith('R-1', 'TVP-1502')
  })

  it('fires onOpenCard with the work order id when the card body is clicked', () => {
    const onOpenCard = vi.fn()
    render(
      <KanbanBoard
        columns={columns}
        onApproveTicket={() => {}}
        onOpenCard={onOpenCard}
        onReviewGate={() => {}}
      />
    )
    fireEvent.click(screen.getByText('Cache headers'))
    expect(onOpenCard).toHaveBeenCalledWith('WO-3')
  })

  it('renders the title of sprint cards without work order as a Jira link', () => {
    render(
      <JiraBrowseProvider baseUrl="https://jira.example.com">
        <KanbanBoard
          columns={columns}
          onApproveTicket={() => {}}
          onOpenCard={() => {}}
          onReviewGate={() => {}}
        />
      </JiraBrowseProvider>
    )
    const link = screen.getByText('Pagination guide TV').closest('a')
    expect(link).toBeTruthy()
    expect(link!.getAttribute('href')).toBe('https://jira.example.com/browse/TVP-1502')
    expect(screen.getByText('Cache headers').closest('a')).toBeNull()
  })

  it('opens the card with the keyboard', () => {
    const onOpenCard = vi.fn()
    render(
      <KanbanBoard
        columns={columns}
        onApproveTicket={() => {}}
        onOpenCard={onOpenCard}
        onReviewGate={() => {}}
      />
    )
    fireEvent.keyDown(screen.getByText('Cache headers').closest('[role="button"]')!, { key: 'Enter' })
    expect(onOpenCard).toHaveBeenCalledWith('WO-3')
  })
})
