import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { approveMrDraft, rejectMrDraft } from '@/lib/delivery'

import { MrDraftReviewPanel } from './mr-draft-review-panel'
import type { DeliveryGate, WorkOrder } from './types'

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
  approveMrDraft: vi.fn().mockResolvedValue(undefined),
  rejectMrDraft: vi.fn().mockResolvedValue(undefined)
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

const workOrder: WorkOrder = {
  id: 'WO-1',
  jiraKey: 'GH-9',
  title: 'Add OAuth callback',
  description: 'Store token after OAuth completes.',
  priority: 'High',
  status: 'awaiting_gate',
  currentStage: 'mr_review',
  confidence: 0.82,
  createdAt: '2026-06-09T10:00:00+00:00',
  updatedAt: '2026-06-09T10:05:00+00:00',
  gates: []
}

describe('MrDraftReviewPanel', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows GitHub PR labels and link text when provider is github', async () => {
    const gate: DeliveryGate = {
      id: 'G-1',
      workOrderId: 'WO-1',
      gateType: 'merge_request_review',
      status: 'pending',
      createdAt: '2026-06-09T10:05:00+00:00',
      payload: {
        draftId: 'DR-1',
        title: 'Add OAuth callback',
        reviewRequestProvider: 'github',
        reviewRequestUrl: 'https://github.com/org/app/pull/42',
        reviewRequestNumber: 42
      }
    }

    render(
      <MrDraftReviewPanel
        gate={gate}
        onDecision={vi.fn().mockResolvedValue(undefined)}
        onOpenChange={() => undefined}
        open
        workOrder={workOrder}
      />
    )

    expect(screen.getByText('PR Draft Review')).toBeTruthy()
    expect(screen.getByText(/Is this PR ready to exist\?/)).toBeTruthy()
    expect(screen.getByTestId('mr-draft-review-link').textContent).toContain('Voir la PR #42 sur GitHub')
  })

  it('falls back to GitLab MR labels from mrUrl and mrIid', () => {
    const gate: DeliveryGate = {
      id: 'G-2',
      workOrderId: 'WO-1',
      gateType: 'merge_request_review',
      status: 'pending',
      createdAt: '2026-06-09T10:05:00+00:00',
      payload: {
        draftId: 'DR-2',
        title: 'Fix player bug',
        mrUrl: 'https://gitlab.example.com/group/repo/-/merge_requests/12',
        mrIid: 12
      }
    }

    render(
      <MrDraftReviewPanel
        gate={gate}
        onDecision={vi.fn().mockResolvedValue(undefined)}
        onOpenChange={() => undefined}
        open
        workOrder={workOrder}
      />
    )

    expect(screen.getByText('MR Draft Review')).toBeTruthy()
    expect(screen.getByTestId('mr-draft-review-link').textContent).toContain('Voir la MR !12 sur GitLab')
  })

  it('falls back to the project provider when the payload omits provider', () => {
    const gate: DeliveryGate = {
      id: 'G-4',
      workOrderId: 'WO-1',
      gateType: 'merge_request_review',
      status: 'pending',
      createdAt: '2026-06-09T10:05:00+00:00',
      payload: {
        draftId: 'DR-4',
        title: 'Fix player bug'
      }
    }

    render(
      <MrDraftReviewPanel
        gate={gate}
        onDecision={vi.fn().mockResolvedValue(undefined)}
        onOpenChange={() => undefined}
        open
        vcsProvider="github"
        workOrder={workOrder}
      />
    )

    expect(screen.getByText('PR Draft Review')).toBeTruthy()
    expect(screen.getByText(/Is this PR ready to exist\?/)).toBeTruthy()
  })

  it('approves draft with provider-aware success message', async () => {
    const gate: DeliveryGate = {
      id: 'G-3',
      workOrderId: 'WO-1',
      gateType: 'merge_request_review',
      status: 'pending',
      createdAt: '2026-06-09T10:05:00+00:00',
      payload: {
        draftId: 'DR-3',
        title: 'Fix player bug',
        reviewRequestProvider: 'github'
      }
    }

    render(
      <MrDraftReviewPanel
        gate={gate}
        onDecision={vi.fn().mockResolvedValue(undefined)}
        onOpenChange={() => undefined}
        open
        workOrder={workOrder}
      />
    )

    fireEvent.click(screen.getByTestId('mr-draft-approve'))

    await waitFor(() => {
      expect(approveMrDraft).toHaveBeenCalledWith('DR-3')
    })
  })
})
