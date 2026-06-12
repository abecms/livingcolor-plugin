import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { dashboardOutlineButtonProps, dashboardPrimaryButtonProps, DASHBOARD_SHEET_BODY_CLASS, DASHBOARD_SHEET_HEADER_CLASS } from './dashboard-ui'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { approveDeliveryGate, rejectDeliveryGate } from '@/lib/delivery'
import { notify, notifyError } from '@/store/notifications'

import { asAnalysisPlanPayload } from './gate-payload'
import { sectionsFromJiraContextUsed } from './gate-payload-formatters'
import { GatePayloadSections } from './gate-payload-sections'
import type { DeliveryGate, WorkOrder } from './types'

export function GateReviewPanel({
  gate,
  onDecision,
  onOpenChange,
  open,
  workOrder
}: {
  gate: DeliveryGate | null
  onDecision: () => void | Promise<void>
  onOpenChange: (open: boolean) => void
  open: boolean
  workOrder: WorkOrder | null
}) {
  const [feedback, setFeedback] = useState('')
  const [busy, setBusy] = useState(false)

  if (!workOrder || !gate) {
    return null
  }

  const payload = asAnalysisPlanPayload(gate.payload)

  const approve = async () => {
    setBusy(true)
    try {
      await approveDeliveryGate(gate.id)
      notify({ kind: 'success', message: `Gate approved for ${workOrder.id}.` })
      setFeedback('')
      onOpenChange(false)
      await onDecision()
    } catch (error) {
      notifyError(error, 'Could not approve gate')
    } finally {
      setBusy(false)
    }
  }

  const reject = async () => {
    const trimmed = feedback.trim()
    if (!trimmed) {
      notifyError(new Error('Feedback is required'), 'Explain what should change before rejecting')
      return
    }

    setBusy(true)
    try {
      await rejectDeliveryGate(gate.id, trimmed)
      notify({ kind: 'success', message: `Gate rejected for ${workOrder.id}. Planning will rerun.` })
      setFeedback('')
      onOpenChange(false)
      await onDecision()
    } catch (error) {
      notifyError(error, 'Could not reject gate')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet onOpenChange={onOpenChange} open={open}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl" side="right">
        <SheetHeader className={DASHBOARD_SHEET_HEADER_CLASS}>
          <SheetTitle>Analysis + Plan Review</SheetTitle>
          <SheetDescription>
            {workOrder.id} · {workOrder.jiraKey} · Gate 1
          </SheetDescription>
        </SheetHeader>

        <div className={DASHBOARD_SHEET_BODY_CLASS} data-testid="gate-review-panel">
          <PlanSection label="Ticket understanding" value={payload.ticketUnderstanding} />
          <PlanSection label="Target repository" value={payload.targetRepo} />
          <PlanSection label="Implementation plan" value={payload.implementationPlan} preformatted />
          <PlanList label="Likely impacted files" items={payload.likelyImpactedFiles} />
          <PlanList label="Risks" items={payload.risks} />
          <PlanSection
            label="Confidence"
            value={
              typeof payload.confidenceLevel === 'number'
                ? `${Math.round(payload.confidenceLevel * 100)}%`
                : undefined
            }
          />
          {payload.jiraContextUsed ? (
            <GatePayloadSections sections={sectionsFromJiraContextUsed(payload.jiraContextUsed)} />
          ) : null}

          <div className="space-y-2">
            <label className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)" htmlFor="gate-feedback">
              Rejection feedback
            </label>
            <Textarea
              data-testid="gate-feedback-input"
              id="gate-feedback"
              onChange={event => setFeedback(event.target.value)}
              placeholder="Required if you reject the plan."
              rows={4}
              value={feedback}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button data-testid="gate-approve-button" disabled={busy} onClick={() => void approve()} {...dashboardPrimaryButtonProps()}>
              Approve plan
            </Button>
            <Button data-testid="gate-reject-button" disabled={busy} onClick={() => void reject()} {...dashboardOutlineButtonProps()}>
              Reject and replan
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function PlanSection({
  label,
  preformatted,
  value
}: {
  label: string
  preformatted?: boolean
  value?: string
}) {
  if (!value) {
    return null
  }

  return (
    <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-3">
      <div className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)">{label}</div>
      {preformatted ? (
        <pre className="mt-2 whitespace-pre-wrap text-sm text-foreground">{value}</pre>
      ) : (
        <p className="mt-2 text-sm text-foreground">{value}</p>
      )}
    </div>
  )
}

function PlanList({ items, label }: { items?: string[]; label: string }) {
  if (!items?.length) {
    return null
  }

  return (
    <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-3">
      <div className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)">{label}</div>
      <ul className="mt-2 space-y-1 text-sm text-foreground">
        {items.map(item => (
          <li key={item}>• {item}</li>
        ))}
      </ul>
    </div>
  )
}
