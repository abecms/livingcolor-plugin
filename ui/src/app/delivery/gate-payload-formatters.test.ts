import { describe, expect, it } from 'vitest'

import {
  buildGatePayloadSections,
  decodeHtmlEntities,
  sectionsFromContextPack,
  sectionsFromJiraContextUsed,
  sectionsFromPatchStats,
  sectionsFromQaChecklist
} from './gate-payload-formatters'

describe('decodeHtmlEntities', () => {
  it('decodes common HTML entities', () => {
    expect(decodeHtmlEntities("L&#039;acrobate")).toBe("L'acrobate")
    expect(decodeHtmlEntities('A &amp; B')).toBe('A & B')
  })
})

describe('sectionsFromContextPack', () => {
  it('formats repository context without raw JSON', () => {
    const sections = sectionsFromContextPack({
      identified_repo: 'tv5monde/tv5mondeplus-front',
      acceptance_criteria: ['Encodage UTF-8 requis'],
      build_notes: ['Repository mapped without local checkout_path.'],
      candidate_files: []
    })

    expect(sections.some(section => section.kind === 'text' && section.label === 'Repository')).toBe(true)
    expect(sections.some(section => section.kind === 'list' && section.label === 'Acceptance criteria')).toBe(true)
    expect(sections.some(section => section.kind === 'list' && section.label === 'Build notes')).toBe(true)
    expect(sections.some(section => section.kind === 'list' && section.label === 'Candidate files')).toBe(false)
  })
})

describe('buildGatePayloadSections', () => {
  it('formats repo clarification payloads', () => {
    const sections = buildGatePayloadSections('repo_clarification', {
      clarificationReason:
        'Repository tv5monde/tv5mondeplus-front is mapped for project TVP but no concrete impacted files could be identified.',
      contextPack: {
        acceptance_criteria: ['Encodage de la property “nom_programme”'],
        build_notes: ['Repository tv5monde/tv5mondeplus-front mapped without local checkout_path.'],
        candidate_files: [],
        identified_repo: 'tv5monde/tv5mondeplus-front',
        epic: null
      }
    })

    expect(sections[0]).toMatchObject({
      kind: 'text',
      label: 'Why clarification is needed'
    })
    expect(sections.some(section => section.kind === 'text' && section.label === 'Repository')).toBe(true)
  })

  it('formats jira update payloads', () => {
    const sections = buildGatePayloadSections('jira_update', {
      proposedComment: 'MR merged to main.',
      jiraKey: 'TVP-2258',
      mrUrl: 'https://gitlab.example.com/group/repo/-/merge_requests/12',
      mrIid: 12,
      targetBranch: 'main'
    })

    expect(sections.some(section => section.kind === 'text' && section.label === 'Proposed Jira comment')).toBe(true)
    expect(sections.some(section => section.kind === 'link' && section.label === 'Merge request')).toBe(true)
    expect(
      sections.some(
        section =>
          section.kind === 'keyValue' &&
          section.entries.some(entry => entry.key === 'Target branch' && entry.value === 'main')
      )
    ).toBe(true)
  })
})

describe('sectionsFromJiraContextUsed', () => {
  it('renders summary and metadata as readable sections', () => {
    const sections = sectionsFromJiraContextUsed({
      summary: 'OAuth callback',
      jiraKey: 'AAC-9',
      commentCount: 2,
      acceptanceCriteria: ['Persist token']
    })

    expect(sections.some(section => section.kind === 'text' && section.label === 'Summary')).toBe(true)
    expect(sections.some(section => section.kind === 'list' && section.label === 'Acceptance criteria')).toBe(true)
    expect(
      sections.some(
        section =>
          section.kind === 'keyValue' &&
          section.entries.some(entry => entry.key === 'Jira key' && entry.value === 'AAC-9')
      )
    ).toBe(true)
  })
})

describe('sectionsFromPatchStats', () => {
  it('renders patch stats as labeled key-value rows', () => {
    const sections = sectionsFromPatchStats({
      filesChanged: 3,
      linesAdded: 42,
      linesRemoved: 7
    })

    expect(sections).toHaveLength(1)
    expect(sections[0]).toMatchObject({ kind: 'keyValue', label: 'Patch stats' })
  })
})

describe('sectionsFromQaChecklist', () => {
  it('renders validation checklist as labeled key-value rows', () => {
    const sections = sectionsFromQaChecklist({
      build: 'PASS',
      tests: 'NOT RUN',
      scopeValidation: 'PASS'
    })

    expect(sections[0]).toMatchObject({ kind: 'keyValue', label: 'Validation checklist' })
  })
})
