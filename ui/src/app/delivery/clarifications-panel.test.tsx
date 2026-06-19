import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { PmInboxPayload } from '@/lib/delivery'

import { ClarificationsPanel } from './clarifications-panel'

afterEach(() => {
  cleanup()
})

const items: PmInboxPayload['needsClarification'] = [
  {
    record: {
      id: 'R-7',
      jiraKey: 'TVP-1520',
      projectKey: 'TVP',
      title: 'Search filters broken',
      readinessScore: 0.4,
      readinessStatus: 'needs_clarification',
      analysisSummary: '',
      blockers: [],
      recommendedRepos: [],
      confidence: 0.5,
      createdAt: '2026-06-11T00:00:00Z',
      updatedAt: '2026-06-11T00:00:00Z'
    },
    detectedIssues: ['Missing acceptance criteria'],
    proposal: { id: 'P-1', body: 'Could you add acceptance criteria?', proposalType: 'clarification', status: 'pending' }
  }
]

describe('ClarificationsPanel', () => {
  it('renders ticket, issues and proposed comment when open', () => {
    render(
      <ClarificationsPanel
        actionId={null}
        items={items}
        onOpenChange={() => {}}
        onProposalAction={() => {}}
        open
      />
    )
    expect(screen.getByText('TVP-1520')).toBeTruthy()
    expect(screen.getByText('Missing acceptance criteria')).toBeTruthy()
    expect(screen.getByText('Could you add acceptance criteria?')).toBeTruthy()
  })

  it('forwards approve action with the proposal id', () => {
    const onProposalAction = vi.fn()
    render(
      <ClarificationsPanel
        actionId={null}
        items={items}
        onOpenChange={() => {}}
        onProposalAction={onProposalAction}
        open
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /validate comment/i }))
    expect(onProposalAction).toHaveBeenCalledWith('P-1', 'approve')
  })

  it('renders pending communication proposals and forwards approve action', () => {
    const onProposalAction = vi.fn()
    const proposals: PmInboxPayload['waitingForApproval'] = [
      {
        kind: 'jira_comment',
        proposalId: 'P-9',
        jiraKey: 'TVP-1530',
        label: 'Jira comment for TVP-1530',
        body: 'Proposed text',
        gateId: null,
        workOrderId: null,
        title: null,
        gateType: null,
        proposalType: 'jira_comment',
        createdAt: '2026-06-11T00:00:00Z'
      }
    ]
    render(
      <ClarificationsPanel
        actionId={null}
        items={[]}
        onOpenChange={() => {}}
        onProposalAction={onProposalAction}
        open
        proposals={proposals}
      />
    )
    expect(screen.getByText('Pending communications')).toBeTruthy()
    expect(screen.getByText('TVP-1530')).toBeTruthy()
    expect(screen.getByText('Jira comment for TVP-1530')).toBeTruthy()
    expect(screen.getByText('Proposed text')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /validate comment/i }))
    expect(onProposalAction).toHaveBeenCalledWith('P-9', 'approve')
  })

  it('renders an empty state when there is nothing to review', () => {
    render(
      <ClarificationsPanel
        actionId={null}
        items={[]}
        notReadyItems={[]}
        onOpenChange={() => {}}
        onProposalAction={() => {}}
        open
      />
    )
    expect(screen.getByText(/no sprint tickets need review right now/i)).toBeTruthy()
  })

  it('renders not-ready tickets with blockers', () => {
    render(
      <ClarificationsPanel
        actionId={null}
        items={[]}
        notReadyItems={[
          {
            record: {
              id: 'R-8',
              jiraKey: 'BN-407',
              projectKey: 'BN',
              title: 'Blocked ticket',
              readinessScore: 30,
              readinessStatus: 'not_ready',
              analysisSummary: '',
              blockers: ['Description is too short'],
              recommendedRepos: [],
              confidence: 0.4,
              createdAt: '2026-06-11T00:00:00Z',
              updatedAt: '2026-06-11T00:00:00Z'
            },
            detectedIssues: ['Description is too short'],
            proposal: null
          }
        ]}
        onOpenChange={() => {}}
        onProposalAction={() => {}}
        open
      />
    )
    expect(screen.getByText('Not ready for delivery')).toBeTruthy()
    expect(screen.getByText('BN-407')).toBeTruthy()
    expect(screen.getByText('Description is too short')).toBeTruthy()
  })
})
