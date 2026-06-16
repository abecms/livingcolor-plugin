import { useCallback, useState } from 'react'

import {
  fetchPmInbox,
  runDailyAnalysis,
  type DailyAnalysisResult,
  type PmInboxPayload
} from '@/lib/delivery'
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
const POLL_INTERVAL_MS = 2_000
const POLL_TIMEOUT_MS = 5_400_000

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

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => {
    window.setTimeout(resolve, ms)
  })
}

function isAnalysisAlreadyRunningError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error)
  return /already running/i.test(message)
}

async function waitForDailyAnalysisCompletion(projectKey?: string): Promise<PmInboxPayload> {
  const deadline = Date.now() + POLL_TIMEOUT_MS
  let sawRunning = false

  while (Date.now() < deadline) {
    await sleep(POLL_INTERVAL_MS)
    const inbox = await fetchPmInbox(projectKey)
    const lastRun = inbox.lastRun
    if (!lastRun) {
      continue
    }

    if (lastRun.status === 'running') {
      sawRunning = true
      continue
    }

    if (lastRun.status === 'failed') {
      throw new Error(lastRun.errorMessage?.trim() || 'Daily analysis failed')
    }

    if (lastRun.status === 'completed') {
      return inbox
    }

    if (sawRunning) {
      return inbox
    }
  }

  throw new Error('Daily analysis timed out after 90 minutes')
}

async function finishDailyAnalysis(
  projectKey: string | undefined,
  onSuccess?: () => void | Promise<void>
): Promise<{ status: string; projectKey?: string }> {
  const inbox = await waitForDailyAnalysisCompletion(projectKey)
  bumpProjectConfigRevision()
  const lastRun = inbox.lastRun
  const dispatch = inbox.analysisDispatch
  const summary =
    dispatch != null
      ? `LLM analysis complete: ${lastRun?.jiraSynced ?? 0} in scope, ${dispatch.success} analyzed, ${dispatch.cached} cached, ${dispatch.failed} failed.`
      : lastRun != null
        ? `Daily analysis complete: ${lastRun.jiraSynced ?? 0} in scope, ${lastRun.analyzed ?? 0} analyzed.`
      : 'Daily analysis complete.'
  notify({ kind: 'success', message: summary })
  await onSuccess?.()
  return { status: 'completed', projectKey: inbox.projectKey }
}

export function useDailyAnalysis(onSuccess?: () => void | Promise<void>) {
  const [running, setRunning] = useState(false)

  const run = useCallback(
    async (projectKey?: string) => {
      setRunning(true)
      try {
        let started: Awaited<ReturnType<typeof runDailyAnalysis>>
        try {
          started = await runDailyAnalysis(projectKey)
        } catch (error) {
          if (isAnalysisAlreadyRunningError(error)) {
            notify({
              kind: 'info',
              message: 'Analysis already running. Waiting for completion…'
            })
            return await finishDailyAnalysis(projectKey, onSuccess)
          }
          throw error
        }

        if (started.status === 'started') {
          notify({ kind: 'info', message: 'Daily analysis started…' })
          return await finishDailyAnalysis(projectKey, onSuccess)
        }

        bumpProjectConfigRevision()
        notify({ kind: 'success', message: analysisSuccessMessage(started) })
        await onSuccess?.()
        return started
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
