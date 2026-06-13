import { describe, expect, it } from 'vitest'

import {
  formatCodeReviewColumnTitle,
  formatReviewRequestLinkLabel,
  formatReviewRequestLinkLabelFr,
  formatWorkOrderStageLabel,
  resolveReviewRequestNumber,
  resolveReviewRequestProvider,
  resolveReviewRequestUrl,
  reviewRequestFullLabel
} from './review-request-labels'

describe('review-request-labels', () => {
  it('prefers provider-neutral review request fields with mr fallbacks', () => {
    expect(
      resolveReviewRequestUrl({
        reviewRequestUrl: 'https://github.com/org/app/pull/42',
        mrUrl: 'https://gitlab.example.com/group/repo/-/merge_requests/12'
      })
    ).toBe('https://github.com/org/app/pull/42')

    expect(
      resolveReviewRequestUrl({
        mrUrl: 'https://gitlab.example.com/group/repo/-/merge_requests/12'
      })
    ).toBe('https://gitlab.example.com/group/repo/-/merge_requests/12')

    expect(
      resolveReviewRequestNumber({
        reviewRequestNumber: 42,
        mrIid: 12
      })
    ).toBe(42)

    expect(resolveReviewRequestNumber({ mrIid: 12 })).toBe(12)
    expect(resolveReviewRequestProvider({ reviewRequestProvider: 'github' })).toBe('github')
    expect(resolveReviewRequestProvider({})).toBe('gitlab')
  })

  it('formats GitHub and GitLab link labels', () => {
    expect(formatReviewRequestLinkLabel('github', 42)).toBe('View PR #42 on GitHub')
    expect(formatReviewRequestLinkLabel('gitlab', 12)).toBe('View MR !12 on GitLab')
    expect(formatReviewRequestLinkLabelFr('github', 42)).toBe('Voir la PR #42 sur GitHub')
    expect(formatReviewRequestLinkLabelFr('gitlab', 12)).toBe('Voir la MR !12 sur GitLab')
  })

  it('formats provider-aware stage and column labels', () => {
    expect(formatWorkOrderStageLabel('mr_publication', 'github')).toBe('Publication GitHub')
    expect(formatWorkOrderStageLabel('mr_draft', 'gitlab')).toBe('MR draft')
    expect(formatCodeReviewColumnTitle('github')).toBe('Code/PR')
    expect(formatCodeReviewColumnTitle('gitlab')).toBe('Code/MR')
    expect(reviewRequestFullLabel('github')).toBe('Pull Request')
    expect(reviewRequestFullLabel('gitlab')).toBe('Merge Request')
  })
})
