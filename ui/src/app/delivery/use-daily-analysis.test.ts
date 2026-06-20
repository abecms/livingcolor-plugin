import { describe, expect, it } from 'vitest'

import { buildDailyAnalysisLastRunCaption } from './use-daily-analysis'

describe('buildDailyAnalysisLastRunCaption', () => {
  const now = new Date('2026-06-11T15:30:00')

  it('returns null when there is no last run', () => {
    expect(buildDailyAnalysisLastRunCaption(null, now)).toBeNull()
  })

  it('describes a successful run from today', () => {
    expect(
      buildDailyAnalysisLastRunCaption(
        { status: 'completed', completedAt: '2026-06-11T12:00:00.000Z' },
        now
      )
    ).toMatch(/Analysis run today at .+\./)
  })

  it('describes a failed run with the error message', () => {
    const completedAt = '2026-06-11T12:00:00.000Z'
    const expectedTime = new Intl.DateTimeFormat(undefined, {
      hour: 'numeric',
      minute: '2-digit'
    }).format(new Date(completedAt))

    expect(
      buildDailyAnalysisLastRunCaption(
        {
          status: 'failed',
          completedAt,
          errorMessage: 'Jira MCP is not connected'
        },
        now
      )
    ).toBe(`Analysis failed today at ${expectedTime}: Jira MCP is not connected`)
  })

  it('uses the calendar date when the run happened on another day', () => {
    expect(
      buildDailyAnalysisLastRunCaption(
        { status: 'completed', completedAt: '2026-06-10T09:15:00.000Z' },
        now
      )
    ).toMatch(/Analysis run on Jun 10 at .+\./)
  })
})
