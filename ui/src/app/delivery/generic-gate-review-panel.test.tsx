import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { approveDeliveryGate, rejectDeliveryGate } from '@/lib/delivery'

import { GenericGateReviewPanel } from './generic-gate-review-panel'
import type { DeliveryGate, WorkOrder } from './types'

vi.mock('@/components/ui/sheet', () => ({
  Sheet: ({ children, open }: { children: React.ReactNode; open?: boolean }) => (open ? <div>{children}</div> : null),
  SheetContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>
}))

vi.mock('@/lib/delivery', () => ({
  approveDeliveryGate: vi.fn().mockResolvedValue({ gate: { id: 'G-clarify' }, workOrderId: 'WO-48' }),
  rejectDeliveryGate: vi.fn().mockResolvedValue({ gate: { id: 'G-clarify' }, workOrderId: 'WO-48' })
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

const workOrder: WorkOrder = {
  id: 'WO-48',
  jiraKey: 'TVP-2258',
  title: 'Encoding fix',
  description: 'Fix nom_programme encoding.',
  priority: 'High',
  status: 'awaiting_gate',
  currentStage: 'clarification',
  confidence: 0.5,
  createdAt: '2026-06-09T10:00:00+00:00',
  updatedAt: '2026-06-09T10:05:00+00:00',
  gates: []
}

const clarificationGate: DeliveryGate = {
  id: 'G-clarify',
  workOrderId: 'WO-48',
  gateType: 'repo_clarification',
  status: 'pending',
  createdAt: '2026-06-09T10:05:00+00:00',
  payload: {
    clarificationReason:
      'Repository tv5monde/tv5mondeplus-front is mapped for project TVP but no concrete impacted files could be identified.',
    contextPack: {
      acceptance_criteria: ['Encodage de la property “nom_programme”'],
      build_notes: ['Repository tv5monde/tv5mondeplus-front mapped without local checkout_path.'],
      candidate_files: [],
      identified_repo: 'tv5monde/tv5mondeplus-front',
      epic: null
    }
  }
}

describe('GenericGateReviewPanel', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders clarification payload as readable sections instead of JSON', () => {
    render(
      <GenericGateReviewPanel
        gate={clarificationGate}
        onDecision={() => undefined}
        onOpenChange={() => undefined}
        open
        title="Repository clarification"
        workOrder={workOrder}
      />
    )

    const panel = screen.getByTestId('generic-gate-review-panel')
    expect(within(panel).getByText('Why clarification is needed')).toBeTruthy()
    expect(within(panel).getByText('Repository')).toBeTruthy()
    expect(within(panel).getByText('tv5monde/tv5mondeplus-front')).toBeTruthy()
    expect(within(panel).getByText('Acceptance criteria')).toBeTruthy()
    expect(within(panel).queryByText(/"contextPack"/)).toBeNull()
    expect(within(panel).queryByText(/"clarificationReason"/)).toBeNull()
    expect(screen.getByTestId('clarification-relaunch-button')).toBeTruthy()
    expect(within(panel).getByRole('button', { name: 'Approve' })).toBeTruthy()
    expect(within(panel).getByRole('button', { name: 'Reject' })).toBeTruthy()
  })

  it('relaunches clarification analysis via approve when no hints are provided', async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined)

    render(
      <GenericGateReviewPanel
        gate={clarificationGate}
        onDecision={onDecision}
        onOpenChange={() => undefined}
        open
        title="Repository clarification"
        workOrder={workOrder}
      />
    )

    fireEvent.click(screen.getByTestId('clarification-relaunch-button'))

    await waitFor(() => {
      expect(approveDeliveryGate).toHaveBeenCalledWith('G-clarify')
      expect(rejectDeliveryGate).not.toHaveBeenCalled()
      expect(onDecision).toHaveBeenCalled()
    })
  })

  it('relaunches clarification analysis via reject when replanning hints are provided', async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined)

    render(
      <GenericGateReviewPanel
        gate={clarificationGate}
        onDecision={onDecision}
        onOpenChange={() => undefined}
        open
        title="Repository clarification"
        workOrder={workOrder}
      />
    )

    const panel = screen.getByTestId('generic-gate-review-panel')

    await act(async () => {
      fireEvent.change(within(panel).getByLabelText(/rejection feedback/i), {
        target: { value: 'repo: tv5monde/tv5mondeplus-front' }
      })
    })
    fireEvent.click(screen.getByTestId('clarification-relaunch-button'))

    await waitFor(() => {
      expect(rejectDeliveryGate).toHaveBeenCalledWith('G-clarify', 'repo: tv5monde/tv5mondeplus-front')
      expect(approveDeliveryGate).not.toHaveBeenCalled()
      expect(onDecision).toHaveBeenCalled()
    })
  })
})
