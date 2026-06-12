import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { approveDeliveryGate, rejectDeliveryGate } from '@/lib/delivery'

import { GateReviewPanel } from './gate-review-panel'
import type { DeliveryGate, WorkOrder } from './types'

vi.mock('@/components/ui/sheet', () => ({
  Sheet: ({ children, open }: { children: React.ReactNode; open?: boolean }) => (open ? <div>{children}</div> : null),
  SheetContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>
}))

vi.mock('@/lib/delivery', () => ({
  approveDeliveryGate: vi.fn().mockResolvedValue({
    gate: { id: 'G-1', status: 'approved' },
    workOrderId: 'WO-1'
  }),
  rejectDeliveryGate: vi.fn().mockResolvedValue({
    gate: { id: 'G-1', status: 'rejected' },
    workOrderId: 'WO-1'
  })
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

const workOrder: WorkOrder = {
  id: 'WO-1',
  jiraKey: 'AAC-9',
  title: 'OAuth callback',
  description: 'Store token after OAuth completes.',
  priority: 'High',
  status: 'awaiting_gate',
  currentStage: 'analysis_review',
  confidence: 0.82,
  createdAt: '2026-06-09T10:00:00+00:00',
  updatedAt: '2026-06-09T10:05:00+00:00',
  gates: []
}

const gate: DeliveryGate = {
  id: 'G-1',
  workOrderId: 'WO-1',
  gateType: 'analysis_plan',
  status: 'pending',
  createdAt: '2026-06-09T10:05:00+00:00',
  payload: {
    ticketUnderstanding: 'Implement OAuth callback persistence.',
    targetRepo: 'gitlab.com/org/app',
    implementationPlan: '1. Add callback handler\n2. Persist token',
    likelyImpactedFiles: ['src/auth/callback.ts'],
    risks: ['Missing migration plan'],
    confidenceLevel: 0.81,
    jiraContextUsed: { jiraKey: 'AAC-9', summary: 'OAuth callback' }
  }
}

describe('GateReviewPanel', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders analysis plan fields and calls approve API', async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined)

    render(
      <GateReviewPanel
        gate={gate}
        onDecision={onDecision}
        onOpenChange={() => undefined}
        open
        workOrder={workOrder}
      />
    )

    const panel = screen.getAllByTestId('gate-review-panel')[0]
    expect(within(panel).getByText('Implement OAuth callback persistence.')).toBeTruthy()
    fireEvent.click(within(panel).getByTestId('gate-approve-button'))

    await waitFor(() => {
      expect(approveDeliveryGate).toHaveBeenCalledWith('G-1')
      expect(onDecision).toHaveBeenCalled()
    })
  })

  it('calls reject API with feedback', async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined)

    render(
      <GateReviewPanel
        gate={gate}
        onDecision={onDecision}
        onOpenChange={() => undefined}
        open
        workOrder={workOrder}
      />
    )

    const panel = screen.getAllByTestId('gate-review-panel')[0]

    await act(async () => {
      fireEvent.input(within(panel).getByTestId('gate-feedback-input'), {
        target: { value: 'Add migration plan' }
      })
    })
    await act(async () => {
      fireEvent.click(within(panel).getByTestId('gate-reject-button'))
    })

    await waitFor(() => {
      expect(rejectDeliveryGate).toHaveBeenCalledWith('G-1', 'Add migration plan')
      expect(onDecision).toHaveBeenCalled()
    })
  })
})
