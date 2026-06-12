import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import type { PmInboxPayload } from '@/lib/delivery'

import {
  DashboardActionRow,
  DASHBOARD_SHEET_BODY_CLASS,
  DASHBOARD_SHEET_HEADER_CLASS,
  ProseBlock,
  TicketKeyBadge,
  dashboardOutlineButtonProps,
  dashboardPrimaryButtonProps
} from './dashboard-ui'
import { JiraTicketTitleLink } from './jira-ticket-link'

export function ClarificationsPanel({
  actionId,
  items,
  onOpenChange,
  onProposalAction,
  open,
  proposals = []
}: {
  actionId: string | null
  items: PmInboxPayload['needsClarification']
  onOpenChange: (open: boolean) => void
  onProposalAction: (proposalId: string, action: 'approve' | 'reject') => void
  open: boolean
  proposals?: PmInboxPayload['waitingForApproval']
}) {
  const pendingProposals = proposals.filter(item => item.proposalId)
  return (
    <Sheet onOpenChange={onOpenChange} open={open}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader className={DASHBOARD_SHEET_HEADER_CLASS}>
          <SheetTitle>Tickets requiring clarification</SheetTitle>
          <SheetDescription>
            Tickets missing acceptance criteria or needing PM input, with proposed Jira comments.
          </SheetDescription>
        </SheetHeader>
        <div className={`${DASHBOARD_SHEET_BODY_CLASS} space-y-4`}>
          {items.length === 0 ? (
            <p className="text-sm text-(--ui-text-secondary)">No tickets require clarification.</p>
          ) : (
            items.map(item => {
              const proposalId = item.proposal?.id
              const busy = proposalId != null && actionId === proposalId
              return (
                <div className="rounded-xl border border-border bg-card p-4" key={item.record.id}>
                  <TicketKeyBadge>{item.record.jiraKey}</TicketKeyBadge>
                  <JiraTicketTitleLink
                    className="mt-2 block text-sm font-medium text-foreground"
                    jiraKey={item.record.jiraKey}
                  >
                    {item.record.title}
                  </JiraTicketTitleLink>
                  {item.detectedIssues.length ? (
                    <ul className="mt-3 space-y-1.5 text-xs text-(--ui-text-secondary)">
                      {item.detectedIssues.map(issue => (
                        <li className="flex gap-2" key={issue}>
                          <span className="mt-1.5 size-1 shrink-0 rounded-full bg-muted-foreground" />
                          <span>{issue}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {item.proposal?.body ? (
                    <>
                      <div className="mt-4 text-[11px] font-medium uppercase tracking-[0.12em] text-(--ui-text-tertiary)">
                        Proposed Jira comment
                      </div>
                      <ProseBlock>{item.proposal.body}</ProseBlock>
                    </>
                  ) : (
                    <p className="mt-4 text-xs text-(--ui-text-secondary)">
                      No comment proposal yet. Run daily analysis to generate one.
                    </p>
                  )}
                  {proposalId ? (
                    <DashboardActionRow>
                      <Button
                        disabled={busy}
                        onClick={() => onProposalAction(proposalId, 'approve')}
                        size="sm"
                        {...dashboardPrimaryButtonProps()}
                      >
                        Validate comment
                      </Button>
                      <Button
                        disabled={busy}
                        onClick={() => onProposalAction(proposalId, 'reject')}
                        size="sm"
                        {...dashboardOutlineButtonProps()}
                      >
                        Reject
                      </Button>
                    </DashboardActionRow>
                  ) : null}
                </div>
              )
            })
          )}
          {pendingProposals.length > 0 ? (
            <>
              <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-(--ui-text-tertiary)">
                Pending communications
              </div>
              {pendingProposals.map(item => {
                const proposalId = item.proposalId!
                const busy = actionId === proposalId
                return (
                  <div className="rounded-xl border border-border bg-card p-4" key={proposalId}>
                    {item.jiraKey ? <TicketKeyBadge>{item.jiraKey}</TicketKeyBadge> : null}
                    <div className="mt-2 text-sm font-medium text-foreground">{item.label}</div>
                    {item.body ? <ProseBlock>{item.body}</ProseBlock> : null}
                    <DashboardActionRow>
                      <Button
                        disabled={busy}
                        onClick={() => onProposalAction(proposalId, 'approve')}
                        size="sm"
                        {...dashboardPrimaryButtonProps()}
                      >
                        Validate comment
                      </Button>
                      <Button
                        disabled={busy}
                        onClick={() => onProposalAction(proposalId, 'reject')}
                        size="sm"
                        {...dashboardOutlineButtonProps()}
                      >
                        Reject
                      </Button>
                    </DashboardActionRow>
                  </div>
                )
              })}
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  )
}
