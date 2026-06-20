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
    expect(
      buildDailyAnalysisLastRunCaption(
        {
          status: 'failed',
          completedAt: '2026-06-11T12:00:00.000Z',
          errorMessage: 'Jira MCP is not connected'
        },
        now
      )
    ).toMatch(/^Analysis failed today at .+: Jira MCP is not connected$/)
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
