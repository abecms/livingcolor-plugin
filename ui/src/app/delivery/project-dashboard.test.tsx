import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchPmInbox, fetchWorkOrder, type PmInboxPayload } from '@/lib/delivery'

import { ProjectDeliveryDashboardView } from './project-dashboard'

vi.mock('@/hooks/use-project-workspace', () => ({
  useProjectWorkspace: () => ({
    activeProjectKey: 'BN',
    activeProject: { jiraProjectKey: 'BN', projectName: 'Bibliothèque Numérique' }
  })
}))

vi.mock('@/components/ui/sheet', () => ({
  Sheet: ({ children, open }: { children: React.ReactNode; open?: boolean }) => (open ? <div>{children}</div> : null),
  SheetContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>
}))

const inboxPayload = {
  projectKey: 'BN',
  projectName: 'Bibliothèque Numérique',
  productIdentity: 'Autonomous Development Scheduler',
  lastRun: null,
  recommendedNext: null,
  currentActiveDelivery: null,
  executionQueue: {
    items: [
      {
        readinessId: 'RD-1',
        jiraKey: 'BN-441',
        title: 'Audio player insight bug',
        queueStatus: 'executable',
        priorityScore: 82,
        estimatedDays: 2,
        blockers: [],
        priorityFactors: {},
        position: 1,
        recommendedNext: true
      }
    ],
    executableCount: 1,
    blockedCount: 0
  },
  selectedSprint: {
    sprintName: 'LivingColor Sprint',
    capacityDays: 15,
    usedDays: 2,
    durationDays: 14,
    overflowRisk: false,
    warnings: [],
    tickets: [
      {
        readinessId: 'RD-1',
        jiraKey: 'BN-441',
        title: 'Audio player insight bug',
        estimatedDays: 2,
        priorityRank: 1,
        urgencyScore: 4.2,
        warnings: []
      }
    ]
  },
  needsClarification: [
    {
      record: {
        id: 'RD-2',
        jiraKey: 'BN-513',
        title: 'Needs more detail',
        readinessStatus: 'needs_clarification'
      },
      detectedIssues: ['Reproduction steps are missing'],
      proposal: {
        id: 'JP-1',
        body: 'Please provide reproduction steps.',
        proposalType: 'needs_clarification',
        status: 'pending'
      }
    }
  ],
  waitingForApproval: [
    {
      kind: 'gate',
      gateId: 'G-1',
      workOrderId: 'WO-1',
      jiraKey: 'BN-441',
      title: 'Audio player insight bug',
      gateType: 'analysis_plan',
      label: 'Analysis validation',
      createdAt: '2026-06-09T10:00:00+00:00'
    }
  ],
  activeDevelopments: [],
  projectMemoryHighlights: []
} as unknown as PmInboxPayload

const emptyInboxPayload = {
  projectKey: 'BN',
  projectName: 'Bibliothèque Numérique',
  productIdentity: 'Autonomous Development Scheduler',
  lastRun: null,
  recommendedNext: null,
  currentActiveDelivery: null,
  executionQueue: { items: [], executableCount: 0, blockedCount: 0 },
  selectedSprint: {
    sprintName: 'LivingColor Sprint',
    capacityDays: 15,
    usedDays: 0,
    durationDays: 14,
    overflowRisk: false,
    warnings: [],
    tickets: []
  },
  needsClarification: [],
  waitingForApproval: [],
  activeDevelopments: [],
  projectMemoryHighlights: []
} as unknown as PmInboxPayload

vi.mock('@/lib/delivery', () => ({
  fetchPmInbox: vi.fn(),
  fetchProjectConfig: vi.fn().mockResolvedValue({
    projectKey: 'BN',
    projectName: 'Bibliothèque Numérique',
    sprintDurationDays: 14,
    sprintCapacityDays: 15,
    communicationLanguage: 'en',
    ticketScope: { statusGroups: ['todo'], assignees: [], includeUnassigned: true, matchMode: 'all' },
    configPath: '/tmp/project.yaml',
    vcs: 'gitlab'
  }),
  fetchDeliveryOverview: vi.fn().mockResolvedValue({
    readiness: { items: [] },
    workOrders: { items: [] },
    recentEvents: { items: [] }
  }),
  fetchWorkOrder: vi.fn().mockResolvedValue({
    id: 'WO-1',
    jiraKey: 'BN-441',
    title: 'Audio player insight bug',
    status: 'awaiting_gate',
    currentStage: 'analysis_review',
    gates: [
      {
        id: 'G-1',
        workOrderId: 'WO-1',
        gateType: 'analysis_plan',
        status: 'pending',
        createdAt: '2026-06-09T10:00:00+00:00',
        payload: {
          ticketUnderstanding: 'Fix insight tracking in the audio player.',
          targetRepo: 'gitlab.com/org/app',
          implementationPlan: '1. Patch player events',
          likelyImpactedFiles: ['src/player.ts'],
          risks: ['Regression on seek'],
          confidenceLevel: 0.8
        }
      }
    ]
  }),
  fetchMrDraft: vi.fn().mockResolvedValue(null),
  decideCommentProposal: vi.fn(),
  promoteReadinessRecord: vi.fn().mockResolvedValue({
    readiness: { id: 'RD-1', jiraKey: 'BN-441', readinessStatus: 'promoted' },
    workOrder: { id: 'WO-2', jiraKey: 'BN-441', status: 'awaiting_gate' }
  }),
  resumeWorkOrder: vi.fn(),
  runDailyAnalysis: vi.fn().mockResolvedValue({
    scan: { scanned: 5 },
    qualification: { estimated: 2 },
    selectedSprint: { tickets: [{ jiraKey: 'BN-1' }] }
  }),
  approveDeliveryGate: vi.fn(),
  rejectDeliveryGate: vi.fn(),
  approveMrDraft: vi.fn(),
  rejectMrDraft: vi.fn(),
  workOrderNeedsResume: () => false,
  findLatestApprovedAnalysisGate: () => undefined,
  findPendingAnalysisGate: (workOrder: { gates?: Array<{ gateType: string; status: string }> }) =>
    workOrder.gates?.find(gate => gate.gateType === 'analysis_plan' && gate.status === 'pending'),
  findPendingCodeReviewGate: () => undefined,
  findPendingMrDraftGate: () => undefined,
  findReviewableMrDraftGate: async () => undefined
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

afterEach(() => {
  cleanup()
  vi.mocked(fetchPmInbox).mockReset()
})

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={['/projects/BN']}>
      <ProjectDeliveryDashboardView />
    </MemoryRouter>
  )
}

describe('ProjectDeliveryDashboardView', () => {
  it('renders the kanban columns', async () => {
    vi.mocked(fetchPmInbox).mockResolvedValue(emptyInboxPayload)
    renderDashboard()

    expect(await screen.findByText('Sprint · 0')).toBeTruthy()
    expect(screen.getByText('Plan · 0')).toBeTruthy()
    expect(screen.getByText('Dev · 0')).toBeTruthy()
    expect(screen.getByText('Code/MR · 0')).toBeTruthy()
    expect(screen.getByText('Jira · 0')).toBeTruthy()
    expect(screen.getByText('Done · 0')).toBeTruthy()
  })

  it('renders sprint strip, gate cards, and clarification actions', async () => {
    vi.mocked(fetchPmInbox).mockResolvedValue(inboxPayload)
    renderDashboard()

    expect(await screen.findByRole('heading', { name: 'Project Dashboard' })).toBeTruthy()
    expect(await screen.findByText('LivingColor Sprint')).toBeTruthy()
    expect(screen.getAllByText('BN-441').length).toBeGreaterThan(0)
    expect(screen.getByText('Plan · 1')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Review plan' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '1 to clarify' }))
    expect(await screen.findByText('Tickets requiring clarification')).toBeTruthy()
    expect(screen.getByText('Validate comment')).toBeTruthy()
  })

  it('opens analysis review from a plan gate card', async () => {
    vi.mocked(fetchPmInbox).mockResolvedValue(inboxPayload)
    renderDashboard()
    await screen.findByRole('heading', { name: 'Project Dashboard' })

    fireEvent.click(await screen.findByRole('button', { name: 'Review plan' }))

    await waitFor(() => {
      expect(fetchWorkOrder).toHaveBeenCalledWith('WO-1')
      expect(screen.getByText('Analysis + Plan Review')).toBeTruthy()
    })
  })
})
