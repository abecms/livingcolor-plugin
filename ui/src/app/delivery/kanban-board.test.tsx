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
        warnings: ['Latest LLM analysis failed; review the error before promotion'],
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

  it('renders the first card warning when present', () => {
    render(
      <KanbanBoard
        columns={columns}
        onApproveTicket={() => {}}
        onOpenCard={() => {}}
        onReviewGate={() => {}}
      />
    )
    expect(screen.getByText('Latest LLM analysis failed; review the error before promotion')).toBeTruthy()
  })

  it('renders warnings with theme-aware contrast classes', () => {
    render(
      <KanbanBoard
        columns={columns}
        onApproveTicket={() => {}}
        onOpenCard={() => {}}
        onReviewGate={() => {}}
      />
    )
    const warning = screen.getByText('Latest LLM analysis failed; review the error before promotion')
    expect(warning.className).toContain('text-amber-800')
    expect(warning.className).toContain('dark:text-amber-100')
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
    fireEvent.click(screen.getByText('TVP-1510'))
    expect(onOpenCard).toHaveBeenCalledWith('WO-3')
  })

  it('renders every card title as a Jira link when a browse base URL is configured', () => {
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
    expect(screen.getByTitle('Open TVP-1502 in Jira')).toBeTruthy()
    expect(screen.getByTitle('Open TVP-1510 in Jira')).toBeTruthy()
  })

  it('does not open the work order when the Jira title link is clicked', () => {
    const onOpenCard = vi.fn()
    render(
      <JiraBrowseProvider baseUrl="https://jira.example.com">
        <KanbanBoard
          columns={columns}
          onApproveTicket={() => {}}
          onOpenCard={onOpenCard}
          onReviewGate={() => {}}
        />
      </JiraBrowseProvider>
    )
    fireEvent.click(screen.getByTitle('Open TVP-1510 in Jira'))
    expect(onOpenCard).not.toHaveBeenCalled()
  })

  it('does not nest the Jira title link inside the keyboard-open control', () => {
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

    expect(screen.getByTitle('Open TVP-1510 in Jira').closest('[role="button"]')).toBeNull()
  })

  it('opens the card with a dedicated keyboard control', () => {
    const onOpenCard = vi.fn()
    render(
      <KanbanBoard
        columns={columns}
        onApproveTicket={() => {}}
        onOpenCard={onOpenCard}
        onReviewGate={() => {}}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Open TVP-1510 work order' }))
    expect(onOpenCard).toHaveBeenCalledWith('WO-3')
  })
})
