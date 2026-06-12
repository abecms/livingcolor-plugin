import { Button } from '@/components/ui/button'
import type { PmInboxPayload } from '@/lib/delivery'
import { AlertTriangle } from '@/lib/icons'
import { cn } from '@/lib/utils'

import { StatusPill, dashboardPrimaryButtonProps } from './dashboard-ui'

export function SprintHeaderStrip({
  analysisRunning,
  clarificationCount,
  onOpenClarifications,
  onRunAnalysis,
  sprint
}: {
  analysisRunning: boolean
  clarificationCount: number
  onOpenClarifications: () => void
  onRunAnalysis: () => void
  sprint: PmInboxPayload['selectedSprint'] | null
}) {
  const pct = sprint
    ? Math.min(100, Math.round((sprint.usedDays / Math.max(sprint.capacityDays, 0.0001)) * 100))
    : 0

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-white/[0.08] bg-white/[0.025] px-4 py-3 backdrop-blur-sm">
      {sprint ? (
        <>
          <span className="text-sm font-semibold text-white">{sprint.sprintName}</span>
          <span className="text-xs tabular-nums text-(--ui-text-secondary)">
            {sprint.usedDays}d / {sprint.capacityDays}d
          </span>
          <div className="h-1.5 min-w-24 flex-1 overflow-hidden rounded-full bg-white/10">
            <div
              className={cn(
                'h-full rounded-full bg-gradient-to-r transition-all duration-500',
                pct >= 95 ? 'from-white/35 to-white/55' : 'from-white/55 to-white/80'
              )}
              style={{ width: `${pct}%` }}
            />
          </div>
          {sprint.overflowRisk ? <StatusPill tone="warning">Overflow risk</StatusPill> : null}
        </>
      ) : (
        <span className="flex-1 text-sm text-(--ui-text-secondary)">No sprint selected yet.</span>
      )}

      {clarificationCount > 0 ? (
        <button
          className="inline-flex items-center gap-1.5 rounded-full border border-white/12 bg-white/[0.04] px-3 py-1 text-xs font-medium text-white/65 transition-colors hover:border-white/25 hover:text-white/90"
          onClick={onOpenClarifications}
          type="button"
        >
          <AlertTriangle className="size-3.5" />
          {clarificationCount} to clarify
        </button>
      ) : null}

      <Button disabled={analysisRunning} onClick={onRunAnalysis} size="sm" {...dashboardPrimaryButtonProps()}>
        {analysisRunning ? 'Running analysis…' : 'Run analysis'}
      </Button>
    </div>
  )
}
