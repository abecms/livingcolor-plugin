export type JiraDashboardTone = 'good' | 'warning' | 'neutral'

export interface JiraDashboardMetric {
  label: string
  value: string
  detail: string
  tone: JiraDashboardTone
}

export interface JiraDashboardAttachment {
  id?: string
  name: string
  mimeType?: string
  previewUrl?: string
  thumbnailUrl?: string
  url?: string
}

export interface JiraDashboardSignal {
  id?: number | null
  signalType: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  reason: string
  confidence: number
  evidenceRefs: string[]
  computedAt: string
}

export interface JiraDashboardIssue {
  key: string
  summary: string
  status: string
  assignee: string
  attachments?: JiraDashboardAttachment[]
  description?: string
  priority?: string
  signals?: JiraDashboardSignal[]
  url?: string
}

export interface JiraDashboardRisk {
  label: string
  detail: string
}

export interface JiraDashboardSignalQuality {
  signalType: string
  total: number
  validated: number
  correct: number
  incorrect: number
  partiallyCorrect: number
  precision: number | null
  falsePositiveRate: number | null
  confidence: 'low' | 'medium' | 'high' | string
}

export interface JiraDashboardValidationSummary {
  ticketKey: string
  signalType: string
  verdict: 'correct' | 'incorrect' | 'partially_correct'
  comment?: string
  validatedBy?: string
  validatedAt?: string
}

export interface JiraDashboardCandidateSignal {
  id?: number | null
  signalType: string
  title: string
  reason: string
  evidence: Record<string, unknown>
  status: 'proposed' | 'accepted' | 'rejected' | 'implemented' | string
  createdAt: string
}

export interface JiraDashboardGeneratedInsight {
  id?: number | null
  insightType: string
  title: string
  conclusion: string
  method: string
  evidence: Record<string, unknown>
  confidence: 'low' | 'medium' | 'high' | string
  sampleSize: number
  sourceRefs: string[]
  generatedAt: string
}

export interface JiraDashboardPMInboxItem {
  ticketKey: string
  summary: string
  attentionScore: number
  riskLevel: 'none' | 'low' | 'medium' | 'high' | 'critical' | string
  evidence: string[]
  recommendedAction: string
  sourceRefs: string[]
}

export interface JiraDashboardWorkspaceMaturity {
  level: 'new' | 'indexed' | 'analyzed' | 'calibrating' | 'mature' | string
  confidence: number
  reasons: string[]
}

export interface JiraDashboardSyncStatus {
  lastSyncedAt?: string
  status: 'idle' | 'running' | 'success' | 'error'
  message?: string
}

export interface JiraDashboardConnection {
  status: 'connected' | 'disconnected' | 'connecting' | 'error'
  message: string
  authenticated: boolean
  toolCount: number
}

export interface JiraDashboardProject {
  key: string
  name: string
}

export interface JiraDashboardPayload {
  connection: JiraDashboardConnection
  sampleData: boolean
  metrics: JiraDashboardMetric[]
  priorities: JiraDashboardIssue[]
  blockers: JiraDashboardIssue[]
  risks: JiraDashboardRisk[]
  signalQuality?: JiraDashboardSignalQuality[]
  falsePositives?: JiraDashboardValidationSummary[]
  falseNegatives?: JiraDashboardValidationSummary[]
  candidateSignals?: JiraDashboardCandidateSignal[]
  generatedInsights?: JiraDashboardGeneratedInsight[]
  pmInbox?: JiraDashboardPMInboxItem[]
  workspaceMaturity?: JiraDashboardWorkspaceMaturity
  actions: string[]
  projects: JiraDashboardProject[]
  selectedProjectKey: string | null
  sprintHealth?: JiraDashboardMetric
  syncStatus?: JiraDashboardSyncStatus
}

export interface JiraIssueAttachmentsResponse {
  attachments: JiraDashboardAttachment[]
}

export interface JiraAttachmentPreviewResponse {
  dataUrl: string
  mimeType: string
}

export interface JiraConnectResponse {
  ok: boolean
  status: JiraDashboardConnection['status']
  message: string
  authenticated: boolean
  toolCount: number
  jiraUrl?: string | null
  saved?: boolean
}

export interface JiraConnectionStatus {
  ok: boolean
  status: JiraDashboardConnection['status']
  message: string
  authenticated: boolean
  toolCount: number
  jiraUrl?: string | null
}
