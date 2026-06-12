import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { dashboardOutlineButtonProps, dashboardPrimaryButtonProps, DASHBOARD_SHEET_BODY_CLASS, DASHBOARD_SHEET_HEADER_CLASS } from './dashboard-ui'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { useWorkOrderLock } from '@/hooks/use-work-order-lock'
import { approveDeliveryGate, rejectDeliveryGate } from '@/lib/delivery'
import { notify, notifyError } from '@/store/notifications'

import { buildGatePayloadSections } from './gate-payload-formatters'
import { GatePayloadSections } from './gate-payload-sections'
import type { DeliveryGate, WorkOrder } from './types'
import { WorkOrderLockNotice } from './work-order-lock-notice'

export function GenericGateReviewPanel({
  gate,
  onDecision,
  onOpenChange,
  open,
  title,
  workOrder
}: {
  gate: DeliveryGate | null
  onDecision: () => void | Promise<void>
  onOpenChange: (open: boolean) => void
  open: boolean
  title: string
  workOrder: WorkOrder | null
}) {
  const [feedback, setFeedback] = useState('')
  const [busy, setBusy] = useState(false)
  const { canWrite, lockMessage } = useWorkOrderLock(workOrder?.id)

  if (!workOrder || !gate) {
    return null
  }

  const isClarificationGate = gate.gateType === 'repo_clarification'

  const approve = async () => {
    setBusy(true)
    try {
      await approveDeliveryGate(gate.id)
      notify({ kind: 'success', message: `Gate approved for ${workOrder.jiraKey}.` })
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
      notify({ kind: 'success', message: `Gate rejected for ${workOrder.jiraKey}.` })
      setFeedback('')
      onOpenChange(false)
      await onDecision()
    } catch (error) {
      notifyError(error, 'Could not reject gate')
    } finally {
      setBusy(false)
    }
  }

  const relaunchAnalysis = async () => {
    const trimmed = feedback.trim()
    setBusy(true)
    try {
      if (trimmed) {
        await rejectDeliveryGate(gate.id, trimmed)
        notify({ kind: 'success', message: `Analysis relaunched for ${workOrder.jiraKey} with your hints.` })
      } else {
        await approveDeliveryGate(gate.id)
        notify({ kind: 'success', message: `Analysis relaunched for ${workOrder.jiraKey}.` })
      }
      setFeedback('')
      onOpenChange(false)
      await onDecision()
    } catch (error) {
      notifyError(error, 'Could not relaunch analysis')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet onOpenChange={onOpenChange} open={open}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl" side="right">
        <SheetHeader className={DASHBOARD_SHEET_HEADER_CLASS}>
          <div className="flex items-start justify-between gap-3 pr-8">
            <div className="min-w-0 space-y-1">
              <SheetTitle>{title}</SheetTitle>
              <SheetDescription>
                {workOrder.id} · {workOrder.jiraKey}
              </SheetDescription>
            </div>
            {isClarificationGate ? (
              <Button
                data-testid="clarification-relaunch-button"
                disabled={busy || !canWrite}
                onClick={() => void relaunchAnalysis()}
                size="sm"
                {...dashboardOutlineButtonProps()}
                className="shrink-0"
              >
                Relaunch analysis
              </Button>
            ) : null}
          </div>
        </SheetHeader>

        <div className={DASHBOARD_SHEET_BODY_CLASS} data-testid="generic-gate-review-panel">
          <WorkOrderLockNotice message={lockMessage} />
          <GatePayloadSections sections={buildGatePayloadSections(gate.gateType, gate.payload ?? {})} />

          <div className="space-y-2">
            <label
              className="text-xs font-medium uppercase tracking-[0.14em] text-(--ui-text-tertiary)"
              htmlFor="generic-gate-feedback"
            >
              Rejection feedback
            </label>
            <Textarea
              id="generic-gate-feedback"
              onChange={event => setFeedback(event.target.value)}
              placeholder="Required if you reject this gate."
              rows={4}
              value={feedback}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button disabled={busy || !canWrite} onClick={() => void approve()} {...dashboardPrimaryButtonProps()}>
              Approve
            </Button>
            <Button disabled={busy || !canWrite} onClick={() => void reject()} {...dashboardOutlineButtonProps()}>
              Reject
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
