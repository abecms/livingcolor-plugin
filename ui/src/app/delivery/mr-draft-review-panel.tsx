import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { dashboardOutlineButtonProps, dashboardPrimaryButtonProps, DASHBOARD_SHEET_BODY_CLASS, DASHBOARD_SHEET_HEADER_CLASS } from './dashboard-ui'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { useWorkOrderLock } from '@/hooks/use-work-order-lock'
import { approveMrDraft, rejectMrDraft } from '@/lib/delivery'
import { ExternalLink } from '@/lib/external-link'
import { notify, notifyError } from '@/store/notifications'

import { sectionsFromQaChecklist } from './gate-payload-formatters'
import { GatePayloadSections } from './gate-payload-sections'
import type { DecisionTraceFileDecision, DecisionTracePayload } from './types'
import type { DeliveryGate, WorkOrder } from './types'
import { WorkOrderLockNotice } from './work-order-lock-notice'

export interface MrDraftPayload {
  draftId?: string
  title?: string
  description?: string
  ticketSummary?: string
  implementationSummary?: string
  filesModified?: string[]
  risks?: string[]
  reviewers?: string[]
  qaChecklist?: Record<string, unknown>
  scopeValidation?: Record<string, unknown>
  decisionTrace?: DecisionTracePayload
  mrUrl?: string
  mrIid?: number | null
}

export function asMrDraftPayload(payload: Record<string, unknown>): MrDraftPayload {
  return payload as MrDraftPayload
}

export function MrDraftReviewPanel({
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
  const { canWrite, lockMessage } = useWorkOrderLock(workOrder?.id)

  if (!workOrder || !gate) {
    return null
  }

  const payload = asMrDraftPayload(gate.payload)
  const draftId = payload.draftId ?? ''
  const decisionTrace = payload.decisionTrace

  const approve = async () => {
    if (!draftId) {
      notifyError(new Error('Missing draft id'), 'Could not approve MR draft')
      return
    }
    setBusy(true)
    try {
      await approveMrDraft(draftId)
      notify({ kind: 'success', message: `MR draft approved for ${workOrder.id}.` })
      setFeedback('')
      onOpenChange(false)
      await onDecision()
    } catch (error) {
      notifyError(error, 'Could not approve MR draft')
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
    if (!draftId) {
      notifyError(new Error('Missing draft id'), 'Could not reject MR draft')
      return
    }

    setBusy(true)
    try {
      await rejectMrDraft(draftId, trimmed)
      notify({ kind: 'success', message: `MR draft rejected for ${workOrder.id}.` })
      setFeedback('')
      onOpenChange(false)
      await onDecision()
    } catch (error) {
      notifyError(error, 'Could not reject MR draft')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet onOpenChange={onOpenChange} open={open}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl" side="right">
        <SheetHeader className={DASHBOARD_SHEET_HEADER_CLASS}>
          <SheetTitle>MR Draft Review</SheetTitle>
          <SheetDescription>
            {workOrder.id} · {workOrder.jiraKey} · Is this MR ready to exist?
          </SheetDescription>
        </SheetHeader>

        <div className={DASHBOARD_SHEET_BODY_CLASS} data-testid="mr-draft-review-panel">
          <WorkOrderLockNotice message={lockMessage} />
          {payload.mrUrl ? (
            <p className="text-sm" data-testid="mr-draft-gitlab-link">
              <ExternalLink href={payload.mrUrl}>
                Voir la MR {payload.mrIid != null ? `!${payload.mrIid} ` : ''}sur GitLab
              </ExternalLink>
            </p>
          ) : null}
          <Section label="Title" value={payload.title} />
          <Section label="Ticket summary" preformatted value={payload.ticketSummary} />
          <Section label="Implementation summary" preformatted value={payload.implementationSummary} />

          {decisionTrace ? (
            <DecisionTraceSection decisionTrace={decisionTrace} jiraKey={workOrder.jiraKey} />
          ) : null}

          <ListSection items={payload.filesModified} label="Files modified" />
          <ListSection items={payload.risks} label="Risks" />
          <ListSection items={payload.reviewers} label="Recommended reviewers" />
          {payload.qaChecklist ? (
            <GatePayloadSections sections={sectionsFromQaChecklist(payload.qaChecklist)} />
          ) : null}
          {payload.description ? (
            <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-3">
              <div className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)">Description</div>
              <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap text-xs text-foreground">{payload.description}</pre>
            </div>
          ) : null}

          <div className="space-y-2">
            <label className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)" htmlFor="mr-draft-feedback">
              Rejection feedback
            </label>
            <Textarea
              data-testid="mr-draft-feedback-input"
              id="mr-draft-feedback"
              onChange={event => setFeedback(event.target.value)}
              placeholder="Explain why this draft MR is not ready."
              value={feedback}
            />
          </div>

          <div className="flex gap-2">
            <Button data-testid="mr-draft-approve" disabled={busy || !canWrite} onClick={() => void approve()} {...dashboardPrimaryButtonProps()}>
              Approve Draft
            </Button>
            <Button data-testid="mr-draft-reject" disabled={busy || !canWrite} onClick={() => void reject()} {...dashboardOutlineButtonProps()}>
              Reject Draft
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function DecisionTraceSection({
  decisionTrace,
  jiraKey
}: {
  decisionTrace: DecisionTracePayload
  jiraKey: string
}) {
  return (
    <div className="space-y-4" data-testid="mr-draft-decision-trace">
      <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-3">
        <div className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)">Reasoning summary</div>
        <p className="mt-2 text-sm text-foreground">{decisionTrace.reasoningSummary}</p>
        <p className="mt-3 text-sm font-medium text-foreground">
          Overall confidence: {Math.round(decisionTrace.overallConfidence)}%
        </p>
      </div>

      {decisionTrace.fileDecisions.map(decision => (
        <FileDecisionCard decision={decision} jiraKey={jiraKey} key={decision.path} />
      ))}

      {decisionTrace.rejectedAlternatives.length ? (
        <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-3">
          <div className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)">Rejected alternatives</div>
          <ul className="mt-2 space-y-1 text-sm text-foreground">
            {decisionTrace.rejectedAlternatives.map(path => (
              <li key={path}>• {path}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {decisionTrace.riskAssessment.summary.length ? (
        <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-3">
          <div className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)">Risk assessment</div>
          <ul className="mt-2 space-y-1 text-sm text-foreground">
            {decisionTrace.riskAssessment.summary.map(line => (
              <li key={line}>• {line}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

function FileDecisionCard({ decision, jiraKey }: { decision: DecisionTraceFileDecision; jiraKey: string }) {
  return (
    <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-3">
      <div className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)">
        {jiraKey} · Why this file?
      </div>
      <p className="mt-2 font-mono text-sm text-foreground">{decision.path}</p>
      <ul className="mt-3 space-y-1 text-sm text-foreground">
        {decision.why.map(reason => (
          <li key={reason}>• {reason}</li>
        ))}
      </ul>
      <p className="mt-3 text-sm font-medium text-foreground">Confidence: {Math.round(decision.confidence)}%</p>
      {decision.rejectedAlternatives.length ? (
        <div className="mt-3">
          <div className="text-xs text-(--ui-text-tertiary)">Alternatives rejected:</div>
          <ul className="mt-1 space-y-1 text-sm text-foreground">
            {decision.rejectedAlternatives.map(path => (
              <li key={path}>• {path}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
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
