import { useCallback, useState } from 'react'

import { runDailyAnalysis, type DailyAnalysisResult } from '@/lib/delivery'
import { bumpProjectConfigRevision } from '@/store/project-config'
import { notifyError, notify } from '@/store/notifications'

export type DailyAnalysisLastRun = {
  status: string
  startedAt?: string
  completedAt?: string | null
  errorMessage?: string | null
}

const TIME_FMT = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' })
const DATE_FMT = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' })

function isSameCalendarDay(left: Date, right: Date): boolean {
  return (
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate()
  )
}

function formatRunTimestamp(iso: string, now: Date): { dayLabel: 'today' | 'date'; dateText: string; timeText: string } {
  const when = new Date(iso)
  if (Number.isNaN(when.getTime())) {
    return { dayLabel: 'date', dateText: 'unknown date', timeText: 'unknown time' }
  }

  return {
    dayLabel: isSameCalendarDay(when, now) ? 'today' : 'date',
    dateText: DATE_FMT.format(when),
    timeText: TIME_FMT.format(when)
  }
}

export function buildDailyAnalysisLastRunCaption(
  lastRun: DailyAnalysisLastRun | null | undefined,
  now: Date = new Date()
): string | null {
  if (!lastRun) {
    return null
  }

  const timestamp = lastRun.completedAt ?? lastRun.startedAt
  if (!timestamp) {
    return null
  }

  const { dayLabel, dateText, timeText } = formatRunTimestamp(timestamp, now)
  const whenPhrase = dayLabel === 'today' ? `today at ${timeText}` : `on ${dateText} at ${timeText}`

  if (lastRun.status === 'failed') {
    const detail = lastRun.errorMessage?.trim()
    return detail
      ? `Analysis failed ${whenPhrase}: ${detail}`
      : `Analysis failed ${whenPhrase}.`
  }

  if (lastRun.status === 'running') {
    return `Analysis running since ${dayLabel === 'today' ? timeText : `${dateText} at ${timeText}`}.`
  }

  return `Analysis run ${whenPhrase}.`
}

function analysisSuccessMessage(result: DailyAnalysisResult): string {
  const fetched = result.scan?.fetched ?? result.scan?.scanned ?? 0
  const inScope = result.scan?.inScope ?? 0
  const analyzed = result.qualification?.analyzed ?? 0
  const estimated = result.qualification?.estimated ?? 0
  const sprintTickets = result.selectedSprint?.tickets?.length ?? 0
  const fetchDetail = fetched > inScope ? ` (${fetched} fetched from Jira)` : ''
  return `Daily analysis complete: ${inScope} ticket(s) in scope${fetchDetail}, ${analyzed} analyzed, ${estimated} ready with estimate, ${sprintTickets} in sprint.`
}

export function useDailyAnalysis(onSuccess?: () => void | Promise<void>) {
  const [running, setRunning] = useState(false)

  const run = useCallback(
    async (projectKey?: string) => {
      setRunning(true)
      try {
        const result = await runDailyAnalysis(projectKey)
        bumpProjectConfigRevision()
        notify({ kind: 'success', message: analysisSuccessMessage(result) })
        await onSuccess?.()
        return result
      } catch (error) {
        notifyError(error, 'Daily analysis failed')
        throw error
      } finally {
        setRunning(false)
      }
    },
    [onSuccess]
  )

  return { running, run }
}
