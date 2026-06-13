import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { WorkOrderProgressPanel } from './work-order-progress-panel'
import type { WorkOrder } from './types'

vi.mock('@/components/ui/sheet', () => ({
  Sheet: ({ children, open }: { children: React.ReactNode; open?: boolean }) => (open ? <div>{children}</div> : null),
  SheetContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>
}))

vi.mock('@/hooks/use-work-order-lock', () => ({
  useWorkOrderLock: () => ({ canWrite: true, lockMessage: null })
}))

vi.mock('@/lib/delivery', () => ({
  fetchMrDraft: vi.fn().mockResolvedValue(null),
  fetchWorkOrder: vi.fn(),
  findLatestApprovedAnalysisGate: () => undefined,
  workOrderNeedsResume: () => false
}))

const workOrder: WorkOrder = {
  id: 'WO-1',
  jiraKey: 'GH-9',
  title: 'Add OAuth callback',
  description: 'Store token after OAuth completes.',
  priority: 'High',
  status: 'awaiting_gate',
  currentStage: 'mr_publication',
  confidence: 0.82,
  createdAt: '2026-06-09T10:00:00+00:00',
  updatedAt: '2026-06-09T10:05:00+00:00',
  graphNodes: [
    {
      id: 'NODE-1',
      workOrderId: 'WO-1',
      nodeType: 'mr_creation',
      status: 'running',
      dependsOn: [],
      payload: {}
    }
  ],
  gates: []
}

describe('WorkOrderProgressPanel', () => {
  afterEach(() => {
    cleanup()
  })

  it('uses the project provider fallback for pre-publication PR labels', () => {
    render(
      <WorkOrderProgressPanel
        onOpenChange={() => undefined}
        open
        vcsProvider="github"
        workOrder={workOrder}
      />
    )

    expect(screen.getByText('Publication GitHub')).toBeTruthy()
    expect(screen.getByTestId('work-order-review-publication-pending').textContent).toContain(
      'Publication de la PR en cours'
    )
    expect(screen.getByText('PR draft')).toBeTruthy()
  })
})
