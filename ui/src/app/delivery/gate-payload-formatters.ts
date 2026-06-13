import {
  formatReviewRequestLinkLabel,
  resolveReviewRequestNumber,
  resolveReviewRequestProvider,
  resolveReviewRequestUrl,
  type ReviewRequestProvider,
  reviewRequestFullLabel
} from './review-request-labels'

export type GatePayloadSection =
  | { kind: 'text'; label: string; value: string; preformatted?: boolean }
  | { kind: 'list'; label: string; items: string[] }
  | { kind: 'keyValue'; label: string; entries: Array<{ key: string; value: string }> }
  | { kind: 'link'; label: string; href: string; text: string }

const PATCH_STAT_LABELS: Record<string, string> = {
  filesChanged: 'Files changed',
  linesAdded: 'Lines added',
  linesRemoved: 'Lines removed',
  linesChanged: 'Lines changed',
  hunks: 'Hunks'
}

const QA_CHECKLIST_LABELS: Record<string, string> = {
  build: 'Build',
  tests: 'Tests',
  scopeValidation: 'Scope validation',
  scopePrecision: 'Scope precision',
  scopeRecall: 'Scope recall',
  linesChanged: 'Lines changed',
  filesTouched: 'Files touched'
}

export function decodeHtmlEntities(text: string): string {
  return text
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)))
    .replace(/&#x([0-9a-fA-F]+);/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)))
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#039;|&apos;/g, "'")
}

function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const trimmed = value.trim()
  return trimmed ? decodeHtmlEntities(trimmed) : null
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value
    .map(item => {
      if (typeof item === 'string') {
        return decodeHtmlEntities(item.trim())
      }
      if (item && typeof item === 'object') {
        const record = item as Record<string, unknown>
        const key = asNonEmptyString(record.key) ?? asNonEmptyString(record.jiraKey)
        const summary = asNonEmptyString(record.summary) ?? asNonEmptyString(record.title)
        if (key && summary) {
          return `${key}: ${summary}`
        }
        return key ?? summary
      }
      return null
    })
    .filter((item): item is string => Boolean(item))
}

function humanizeKey(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function formatRecordEntries(
  record: Record<string, unknown>,
  labels: Record<string, string> = {}
): Array<{ key: string; value: string }> {
  return Object.entries(record)
    .map(([key, value]) => {
      if (value == null || value === '') {
        return null
      }
      if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
        return { key: labels[key] ?? humanizeKey(key), value: String(value) }
      }
      return null
    })
    .filter((entry): entry is { key: string; value: string } => entry != null)
}

export function sectionsFromContextPack(contextPack: Record<string, unknown>): GatePayloadSection[] {
  const sections: GatePayloadSection[] = []

  const repo = asNonEmptyString(contextPack.identified_repo)
  if (repo) {
    sections.push({ kind: 'text', label: 'Repository', value: repo })
  }

  const checkoutPath = asNonEmptyString(contextPack.repo_checkout_path)
  if (checkoutPath) {
    sections.push({ kind: 'text', label: 'Checkout path', value: checkoutPath })
  }

  const jiraKey = asNonEmptyString(contextPack.jira_key)
  if (jiraKey) {
    sections.push({ kind: 'text', label: 'Jira key', value: jiraKey })
  }

  const ticket = contextPack.jira_ticket
  if (ticket && typeof ticket === 'object') {
    const ticketRecord = ticket as Record<string, unknown>
    const summary = asNonEmptyString(ticketRecord.summary)
    if (summary) {
      sections.push({ kind: 'text', label: 'Ticket summary', value: summary })
    }
    const description = asNonEmptyString(ticketRecord.description)
    if (description) {
      sections.push({ kind: 'text', label: 'Ticket description', value: description, preformatted: true })
    }
  }

  const epic = contextPack.epic
  if (epic && typeof epic === 'object') {
    const epicRecord = epic as Record<string, unknown>
    const epicKey = asNonEmptyString(epicRecord.key)
    const epicSummary = asNonEmptyString(epicRecord.summary) ?? asNonEmptyString(epicRecord.title)
    const epicLine = [epicKey, epicSummary].filter(Boolean).join(': ')
    if (epicLine) {
      sections.push({ kind: 'text', label: 'Epic', value: epicLine })
    }
  }

  const acceptanceCriteria = asStringList(contextPack.acceptance_criteria)
  if (acceptanceCriteria.length) {
    sections.push({ kind: 'list', label: 'Acceptance criteria', items: acceptanceCriteria })
  }

  const buildNotes = asStringList(contextPack.build_notes)
  if (buildNotes.length) {
    sections.push({ kind: 'list', label: 'Build notes', items: buildNotes })
  }

  const candidateFiles = asStringList(contextPack.candidate_files)
  if (candidateFiles.length) {
    sections.push({ kind: 'list', label: 'Candidate files', items: candidateFiles })
  }

  const conventions = asStringList(contextPack.project_conventions)
  if (conventions.length) {
    sections.push({ kind: 'list', label: 'Project conventions', items: conventions })
  }

  const linkedTickets = asStringList(contextPack.linked_tickets)
  if (linkedTickets.length) {
    sections.push({ kind: 'list', label: 'Linked tickets', items: linkedTickets })
  }

  const gitHistory = asStringList(contextPack.git_history)
  if (gitHistory.length) {
    sections.push({ kind: 'list', label: 'Recent git history', items: gitHistory })
  }

  const rejectionFeedback = asNonEmptyString(contextPack.rejection_feedback)
  if (rejectionFeedback) {
    sections.push({ kind: 'text', label: 'Previous rejection feedback', value: rejectionFeedback, preformatted: true })
  }

  return sections
}

export function sectionsFromJiraContextUsed(value: Record<string, unknown>): GatePayloadSection[] {
  const sections: GatePayloadSection[] = []

  const summary = asNonEmptyString(value.summary)
  if (summary) {
    sections.push({ kind: 'text', label: 'Summary', value: summary })
  }

  const description = asNonEmptyString(value.description)
  if (description) {
    sections.push({ kind: 'text', label: 'Description', value: description, preformatted: true })
  }

  const entries = formatRecordEntries(value, {
    jiraKey: 'Jira key',
    projectKey: 'Project key',
    epicKey: 'Epic key',
    commentCount: 'Comments',
    linkedTicketCount: 'Linked tickets'
  }).filter(entry => !['Summary', 'Description'].includes(entry.key))

  const acceptanceCriteria = asStringList(value.acceptanceCriteria)
  if (acceptanceCriteria.length) {
    sections.push({ kind: 'list', label: 'Acceptance criteria', items: acceptanceCriteria })
  }

  if (entries.length) {
    sections.push({ kind: 'keyValue', label: 'Jira context', entries })
  }

  return sections
}

export function sectionsFromPatchStats(stats: Record<string, unknown>): GatePayloadSection[] {
  const entries = formatRecordEntries(stats, PATCH_STAT_LABELS)
  return entries.length ? [{ kind: 'keyValue', label: 'Patch stats', entries }] : []
}

export function sectionsFromQaChecklist(checklist: Record<string, unknown>): GatePayloadSection[] {
  const entries = formatRecordEntries(checklist, QA_CHECKLIST_LABELS)
  return entries.length ? [{ kind: 'keyValue', label: 'Validation checklist', entries }] : []
}

function sectionsFromJiraUpdatePayload(
  payload: Record<string, unknown>,
  fallbackProvider?: ReviewRequestProvider
): GatePayloadSection[] {
  const sections: GatePayloadSection[] = []

  const proposedComment = asNonEmptyString(payload.proposedComment)
  if (proposedComment) {
    sections.push({ kind: 'text', label: 'Proposed Jira comment', value: proposedComment, preformatted: true })
  }

  const jiraKey = asNonEmptyString(payload.jiraKey)
  if (jiraKey) {
    sections.push({ kind: 'text', label: 'Jira key', value: jiraKey })
  }

  const reviewRequestUrl = resolveReviewRequestUrl(payload)
  const reviewRequestProvider = resolveReviewRequestProvider(payload, fallbackProvider)
  const reviewRequestNumber = resolveReviewRequestNumber(payload)
  if (reviewRequestUrl) {
    const linkText = formatReviewRequestLinkLabel(reviewRequestProvider, reviewRequestNumber ?? undefined)
    sections.push({
      kind: 'link',
      label: reviewRequestFullLabel(reviewRequestProvider),
      href: reviewRequestUrl,
      text: linkText
    })
  }

  const detailPayload = { ...payload }
  delete detailPayload.proposedComment
  delete detailPayload.mrUrl
  delete detailPayload.reviewRequestUrl
  delete detailPayload.jiraKey
  if (reviewRequestUrl) {
    delete detailPayload.mrIid
    delete detailPayload.reviewRequestNumber
    delete detailPayload.reviewRequestProvider
  }

  const reviewNumberLabel =
    reviewRequestProvider === 'github' ? 'PR number' : 'MR number'
  const entries = formatRecordEntries(detailPayload, {
    targetBranch: 'Target branch',
    mrIid: reviewNumberLabel,
    reviewRequestNumber: reviewNumberLabel,
    nodeId: 'Pipeline node'
  })

  if (entries.length) {
    sections.push({ kind: 'keyValue', label: 'Publication details', entries })
  }

  return sections
}

function sectionsFromClarificationPayload(payload: Record<string, unknown>): GatePayloadSection[] {
  const sections: GatePayloadSection[] = []

  const reason = asNonEmptyString(payload.clarificationReason)
  if (reason) {
    sections.push({ kind: 'text', label: 'Why clarification is needed', value: reason, preformatted: true })
  }

  const contextPack = payload.contextPack
  if (contextPack && typeof contextPack === 'object') {
    sections.push(...sectionsFromContextPack(contextPack as Record<string, unknown>))
  }

  return sections
}

function sectionsFromUnknownPayload(payload: Record<string, unknown>): GatePayloadSection[] {
  const sections: GatePayloadSection[] = []

  for (const [key, value] of Object.entries(payload)) {
    if (value == null || value === '') {
      continue
    }
    const label = humanizeKey(key)
    if (typeof value === 'string') {
      sections.push({ kind: 'text', label, value: decodeHtmlEntities(value), preformatted: value.includes('\n') })
      continue
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      sections.push({ kind: 'text', label, value: String(value) })
      continue
    }
    if (Array.isArray(value)) {
      const items = asStringList(value)
      if (items.length) {
        sections.push({ kind: 'list', label, items })
      }
      continue
    }
    if (typeof value === 'object') {
      const entries = formatRecordEntries(value as Record<string, unknown>)
      if (entries.length) {
        sections.push({ kind: 'keyValue', label, entries })
      }
    }
  }

  return sections
}

export function buildGatePayloadSections(
  gateType: string,
  payload: Record<string, unknown>,
  fallbackProvider?: ReviewRequestProvider
): GatePayloadSection[] {
  switch (gateType) {
    case 'repo_clarification':
      return sectionsFromClarificationPayload(payload)
    case 'jira_update':
      return sectionsFromJiraUpdatePayload(payload, fallbackProvider)
    default:
      return sectionsFromUnknownPayload(payload)
  }
}
