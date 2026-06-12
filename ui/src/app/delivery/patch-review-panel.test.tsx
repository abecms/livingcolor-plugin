import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { approveDeliveryGate, rejectDeliveryGate } from '@/lib/delivery'

import { PatchReviewPanel } from './patch-review-panel'
import type { DeliveryGate, WorkOrder } from './types'

vi.mock('@/components/ui/sheet', () => ({
  Sheet: ({ children, open }: { children: React.ReactNode; open?: boolean }) => (open ? <div>{children}</div> : null),
  SheetContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>
}))

vi.mock('@/lib/delivery', () => ({
  approveDeliveryGate: vi.fn(),
  rejectDeliveryGate: vi.fn()
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

const workOrder: WorkOrder = {
  id: 'WO-1',
  jiraKey: 'AAC-42',
  title: 'OAuth callback endpoint',
  description: '',
  priority: 'High',
  status: 'awaiting_gate',
  currentStage: 'code_review',
  confidence: 0.8,
  createdAt: '2026-06-09T00:00:00Z',
  updatedAt: '2026-06-09T00:00:00Z'
}

const gate: DeliveryGate = {
  id: 'G-2',
  workOrderId: 'WO-1',
  gateType: 'code_review',
  status: 'pending',
  createdAt: '2026-06-09T00:00:00Z',
  payload: {
    summary: 'Generated reviewable patch for AAC-42 touching 2 file(s).',
    implementationPlan: '1. Inspect src/auth/oauth_callback.ts',
    filesModified: ['src/auth/oauth_callback.ts'],
    filesCreated: ['tests/test_delivery_aac_42.py'],
    likelyImpactedFiles: ['src/auth/oauth_callback.ts'],
    diffPreview: '+export function deliveryFixAac42() {}',
    confidence: 0.82,
    risks: ['OAuth token persistence needs regression coverage'],
    patchStats: { linesChanged: 12 }
  }
}

describe('PatchReviewPanel', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders patch review details', () => {
    render(
      <PatchReviewPanel
        gate={gate}
        onDecision={vi.fn()}
        onOpenChange={vi.fn()}
        open
        workOrder={workOrder}
      />
    )

    const panel = screen.getAllByTestId('patch-review-panel')[0]
    expect(within(panel).getByText(/Generated reviewable patch/)).toBeTruthy()
    expect(within(panel).getByText(/deliveryFixAac42/)).toBeTruthy()
  })

  it('approves patch through delivery API', async () => {
    vi.mocked(approveDeliveryGate).mockResolvedValue({ gate: { ...gate, status: 'approved' }, workOrderId: 'WO-1' })
    const onDecision = vi.fn().mockResolvedValue(undefined)

    render(
      <PatchReviewPanel gate={gate} onDecision={onDecision} onOpenChange={vi.fn()} open workOrder={workOrder} />
    )

    const panel = screen.getAllByTestId('patch-review-panel')[0]
    await act(async () => {
      fireEvent.click(within(panel).getByTestId('patch-approve-button'))
    })

    await waitFor(() => {
      expect(approveDeliveryGate).toHaveBeenCalledWith('G-2')
      expect(onDecision).toHaveBeenCalled()
    })
  })

  it('rejects patch with structured feedback', async () => {
    vi.mocked(rejectDeliveryGate).mockResolvedValue({ gate: { ...gate, status: 'rejected' }, workOrderId: 'WO-1' })
    const onDecision = vi.fn().mockResolvedValue(undefined)

    render(
      <PatchReviewPanel gate={gate} onDecision={onDecision} onOpenChange={vi.fn()} open workOrder={workOrder} />
    )

    const panel = screen.getAllByTestId('patch-review-panel')[0]

    await act(async () => {
      fireEvent.input(within(panel).getByTestId('patch-feedback-input'), {
        target: { value: 'Handle null user state.' }
      })
    })
    await act(async () => {
      fireEvent.click(within(panel).getByTestId('patch-reject-button'))
    })

    await waitFor(() => {
      expect(rejectDeliveryGate).toHaveBeenCalledWith('G-2', 'Handle null user state.', [
        { type: 'missing_case', message: 'Handle null user state.' }
      ])
      expect(onDecision).toHaveBeenCalled()
    })
  })
})
