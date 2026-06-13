import type { KeyboardEvent, MouseEvent } from 'react'

import { Button } from '@/components/ui/button'
import { formatTicketEstimationHours } from '@/lib/delivery-estimation'
import { cn } from '@/lib/utils'

import { TicketKeyBadge, dashboardPrimaryButtonProps } from './dashboard-ui'
import { JiraTicketTitleLink } from './jira-ticket-link'
import type { KanbanCard, KanbanColumn } from './kanban-routing'
import type { ReviewRequestProvider } from './review-request-labels'
import { formatWorkOrderStage } from './stage-labels'

const COLUMN_ACCENTS = {
  neutral: 'text-muted-foreground',
  warning: 'text-foreground',
  muted: 'text-muted-foreground/70'
} as const

export const KANBAN_COLUMN_MIN_WIDTH = '15.12rem'

const KANBAN_COLUMN_CLASS =
  'flex min-w-[15.12rem] shrink-0 flex-col max-[1280px]:w-[15.12rem] min-[1281px]:min-w-0 min-[1281px]:w-0 min-[1281px]:flex-1 min-[1281px]:basis-0'

export function KanbanBoard({
  className,
  columns,
  onApproveTicket,
  onOpenCard,
  onReviewGate,
  vcsProvider
}: {
  className?: string
  columns: KanbanColumn[]
  onApproveTicket: (readinessId: string, jiraKey: string) => void
  onOpenCard: (workOrderId: string) => void
  onReviewGate: (input: { workOrderId: string; gateId: string; gateType: string }) => void
  vcsProvider?: ReviewRequestProvider
}) {
  return (
    <div
      className={cn(
        'flex min-h-0 flex-1 gap-3 overflow-x-auto overflow-y-hidden pb-2 min-[1281px]:overflow-x-hidden',
        className
      )}
      data-testid="kanban-board"
    >
      {columns.map(column => (
        <div className={KANBAN_COLUMN_CLASS} key={column.id}>
          <div
            className={cn(
              'mb-2 shrink-0 text-[11px] font-medium uppercase tracking-[0.12em]',
              COLUMN_ACCENTS[column.accent]
            )}
          >
            {column.title} · {column.cards.length}
          </div>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-y-contain pr-1">
            {column.cards.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border px-3 py-8 text-center text-[11px] text-muted-foreground opacity-60">
                Empty
              </div>
            ) : (
              column.cards.map(card => (
                <KanbanCardView
                  card={card}
                  isDone={column.id === 'done'}
                  isGate={Boolean(card.gateId)}
                  key={card.id}
                  onApproveTicket={onApproveTicket}
                  onOpenCard={onOpenCard}
                  onReviewGate={onReviewGate}
                  vcsProvider={vcsProvider}
                />
              ))
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function KanbanCardView({
  card,
  isDone,
  isGate,
  onApproveTicket,
  onOpenCard,
  onReviewGate,
  vcsProvider
}: {
  card: KanbanCard
  isDone: boolean
  isGate: boolean
  onApproveTicket: (readinessId: string, jiraKey: string) => void
  onOpenCard: (workOrderId: string) => void
  onReviewGate: (input: { workOrderId: string; gateId: string; gateType: string }) => void
  vcsProvider?: ReviewRequestProvider
}) {
  const clickable = Boolean(card.workOrderId)
  const ctaProps = dashboardPrimaryButtonProps()

  const handleCardClick = () => {
    if (card.workOrderId) {
      onOpenCard(card.workOrderId)
    }
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      handleCardClick()
    }
  }

  const handleCta = (event: MouseEvent) => {
    event.stopPropagation()
    if (isGate && card.gateId && card.workOrderId) {
      onReviewGate({ workOrderId: card.workOrderId, gateId: card.gateId, gateType: card.gateType ?? 'unknown' })
      return
    }
    if (card.readinessId) {
      onApproveTicket(card.readinessId, card.jiraKey)
    }
  }

  return (
    <div
      className={cn(
        'w-full rounded-xl border bg-card p-4 transition-colors',
        isGate ? 'border-ring/50' : 'border-border',
        isDone ? 'opacity-55' : null,
        clickable ? 'cursor-pointer hover:border-ring/40' : null
      )}
      onClick={handleCardClick}
      onKeyDown={clickable ? handleKeyDown : undefined}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
    >
      <TicketKeyBadge>{card.jiraKey}</TicketKeyBadge>
      <div className="mt-2 text-sm font-medium leading-snug text-foreground">
        {card.workOrderId ? (
          card.title
        ) : (
          <JiraTicketTitleLink jiraKey={card.jiraKey}>{card.title}</JiraTicketTitleLink>
        )}
        {isDone ? ' ✓' : ''}
      </div>
      <div className="mt-1.5 space-y-0.5 text-[10px] text-muted-foreground">
        {card.estimatedDays != null ? <div>Estim. {formatTicketEstimationHours(card.estimatedDays)}</div> : null}
        {card.priorityRank != null ? <div>Prio #{card.priorityRank}</div> : null}
        {card.currentStage ? <div>⚙ {formatWorkOrderStage(card.currentStage, vcsProvider)}</div> : null}
      </div>
      {card.ctaLabel ? (
        <Button
          {...ctaProps}
          className={cn(ctaProps.className, 'mt-2 h-6 px-2 text-[10px]')}
          onClick={handleCta}
          size="sm"
        >
          {card.ctaLabel}
        </Button>
      ) : null}
    </div>
  )
}
