import { Button } from '@/components/ui/button'
import type { PmInboxPayload } from '@/lib/delivery'
import { AlertTriangle } from '@/lib/icons'
import { cn } from '@/lib/utils'

import { StatusPill, dashboardPrimaryButtonProps } from './dashboard-ui'

export function SprintHeaderStrip({
  analysisRunning,
  reviewCount,
  onOpenClarifications,
  onRunAnalysis,
  sprint
}: {
  analysisRunning: boolean
  reviewCount: number
  onOpenClarifications: () => void
  onRunAnalysis: () => void
  sprint: PmInboxPayload['selectedSprint'] | null
}) {
  const pct = sprint
    ? Math.min(100, Math.round((sprint.usedDays / Math.max(sprint.capacityDays, 0.0001)) * 100))
    : 0

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-border bg-card px-4 py-3">
      {sprint ? (
        <>
          <span className="text-sm font-semibold text-foreground">{sprint.sprintName}</span>
          <span className="text-xs tabular-nums text-muted-foreground">
            {sprint.usedDays}d / {sprint.capacityDays}d
          </span>
          <div className="h-1.5 min-w-24 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              className={cn(
                'h-full rounded-full bg-gradient-to-r transition-all duration-500',
                pct >= 95 ? 'from-warning/70 to-warning' : 'from-primary/70 to-primary'
              )}
              style={{ width: `${pct}%` }}
            />
          </div>
          {sprint.overflowRisk ? <StatusPill tone="warning">Overflow risk</StatusPill> : null}
        </>
      ) : (
        <span className="flex-1 text-sm text-muted-foreground">No sprint selected yet.</span>
      )}

      {reviewCount > 0 ? (
        <button
          className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/40 px-3 py-1 text-xs font-medium text-muted-foreground transition-colors hover:border-ring/40 hover:text-foreground"
          onClick={onOpenClarifications}
          type="button"
        >
          <AlertTriangle className="size-3.5" />
          {reviewCount} to review
        </button>
      ) : null}

      <Button disabled={analysisRunning} onClick={onRunAnalysis} size="sm" {...dashboardPrimaryButtonProps()}>
        {analysisRunning ? 'Running analysis…' : 'Run analysis'}
      </Button>
    </div>
  )
}
