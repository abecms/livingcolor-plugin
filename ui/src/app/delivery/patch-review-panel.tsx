import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { dashboardOutlineButtonProps, dashboardPrimaryButtonProps, DASHBOARD_SHEET_BODY_CLASS, DASHBOARD_SHEET_HEADER_CLASS } from './dashboard-ui'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { approveDeliveryGate, rejectDeliveryGate } from '@/lib/delivery'
import { notify, notifyError } from '@/store/notifications'

import { sectionsFromPatchStats } from './gate-payload-formatters'
import { GatePayloadSections } from './gate-payload-sections'
import { asCodeReviewPayload } from './patch-payload'
import type { DeliveryGate, WorkOrder } from './types'

export function PatchReviewPanel({
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

  const payload = asCodeReviewPayload(gate.payload)
  const touchedFiles = [...(payload.filesModified ?? []), ...(payload.filesCreated ?? [])]
  const feedbackHistory = (workOrder.gates ?? [])
    .filter(item => item.gateType === 'code_review' && item.status === 'rejected' && item.rejectionFeedback)
    .map(item => item.rejectionFeedback as string)

  const approve = async () => {
    setBusy(true)
    try {
      await approveDeliveryGate(gate.id)
      notify({ kind: 'success', message: `Patch approved for ${workOrder.id}.` })
      setFeedback('')
      onOpenChange(false)
      await onDecision()
    } catch (error) {
      notifyError(error, 'Could not approve patch')
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
      await rejectDeliveryGate(gate.id, trimmed, [{ type: 'missing_case', message: trimmed }])
      notify({ kind: 'success', message: `Patch rejected for ${workOrder.id}. Developer Agent will rerun.` })
      setFeedback('')
      onOpenChange(false)
      await onDecision()
    } catch (error) {
      notifyError(error, 'Could not reject patch')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet onOpenChange={onOpenChange} open={open}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl" side="right">
        <SheetHeader className={DASHBOARD_SHEET_HEADER_CLASS}>
          <SheetTitle>Code Review</SheetTitle>
          <SheetDescription>
            {workOrder.id} · {workOrder.jiraKey} · Is this patch acceptable?
          </SheetDescription>
        </SheetHeader>

        <div className={DASHBOARD_SHEET_BODY_CLASS} data-testid="patch-review-panel">
          <Section label="Patch summary" value={payload.summary} />
          <Section label="Implementation plan" preformatted value={payload.implementationPlan} />
          <ListSection items={touchedFiles} label="Modified files" />
          <ListSection items={payload.likelyImpactedFiles} label="Predicted files" />
          <ListSection items={payload.risks} label="Risks" />
          <Section
            label="Confidence"
            value={typeof payload.confidence === 'number' ? `${Math.round(payload.confidence * 100)}%` : undefined}
          />
          {payload.patchStats ? (
            <GatePayloadSections sections={sectionsFromPatchStats(payload.patchStats)} />
          ) : null}
          {payload.diffPreview ? (
            <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-3">
              <div className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)">Diff preview</div>
              <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs text-foreground">{payload.diffPreview}</pre>
            </div>
          ) : null}
          {feedbackHistory.length ? (
            <ListSection items={feedbackHistory} label="Reviewer feedback history" />
          ) : null}

          <div className="space-y-2">
            <label className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)" htmlFor="patch-feedback">
              Rejection feedback
            </label>
            <Textarea
              data-testid="patch-feedback-input"
              id="patch-feedback"
              onChange={event => setFeedback(event.target.value)}
              placeholder='Example: missing_case: Handle null user state.'
              rows={4}
              value={feedback}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button data-testid="patch-approve-button" disabled={busy} onClick={() => void approve()} {...dashboardPrimaryButtonProps()}>
              Approve patch
            </Button>
            <Button data-testid="patch-reject-button" disabled={busy} onClick={() => void reject()} {...dashboardOutlineButtonProps()}>
              Reject patch
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function Section({
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

function ListSection({ items, label }: { items?: string[]; label: string }) {
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
