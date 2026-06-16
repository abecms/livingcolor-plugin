export type ReadinessStatus =
  | 'pending_analysis'
  | 'analyzed'
  | 'ready'
  | 'not_ready'
  | 'needs_clarification'
  | 'not_development'
  | 'analysis_failed'
  | 'promoted'
  | 'dismissed'

export type WorkOrderStatus = 'intake' | 'running' | 'awaiting_gate' | 'completed' | 'failed' | 'cancelled'

export type WorkOrderStage =
  | 'intake'
  | 'analysis_review'
  | 'clarification'
  | 'development'
  | 'merge_conflict_resolution'
  | 'code_review'
  | 'mr_draft'
  | 'awaiting_next_phase'
  | 'mr_review'
  | 'mr_publication'
  | 'jira_review'
  | 'completed'

export interface ReadinessRecord {
  id: string
  jiraKey: string
  projectKey: string
  title: string
  readinessScore: number
  readinessStatus: ReadinessStatus
  analysisSummary: string
  blockers: string[]
  recommendedRepos: string[]
  confidence: number
  analyzedAt?: string | null
  promotedWorkOrderId?: string | null
  createdAt: string
  updatedAt: string
}

export interface GraphNode {
  id: string
  workOrderId: string
  nodeType: string
  status: string
  dependsOn: string[]
  agentProfile?: string | null
  payload: Record<string, unknown>
  startedAt?: string | null
  completedAt?: string | null
}

export interface DeliveryGate {
  id: string
  workOrderId: string
  gateType: 'analysis_plan' | 'code_review' | 'merge_request_review' | 'merge_request' | 'jira_update' | string
  status: 'pending' | 'approved' | 'rejected' | string
  payload: Record<string, unknown>
  createdAt: string
  approvedAt?: string | null
  approvedBy?: string | null
  rejectionFeedback?: string | null
}

export interface WorkOrder {
  id: string
  jiraKey: string
  readinessId?: string | null
  title: string
  description: string
  priority: string
  status: WorkOrderStatus
  currentStage: WorkOrderStage
  confidence: number
  createdAt: string
  updatedAt: string
  graphNodes?: GraphNode[]
  gates?: DeliveryGate[]
}

export interface DeliveryEvent {
  id: string
  workOrderId?: string | null
  readinessId?: string | null
  eventType: string
  payload: Record<string, unknown>
  actor: string
  createdAt: string
}

export interface DeliveryOverview {
  readiness: { items: ReadinessRecord[] }
  workOrders: { items: WorkOrder[] }
  recentEvents: { items: DeliveryEvent[] }
}

export interface MrDraftRecord {
  id: string
  workOrderId: string
  title: string
  description: string
  ticketSummary: string
  implementationSummary: string
  filesModified: string[]
  risks: string[]
  reviewers: string[]
  qaChecklist: Record<string, unknown>
  decisionTrace?: DecisionTracePayload
  mrUrl?: string
  mrIid?: number | null
  reviewRequestUrl?: string
  reviewRequestNumber?: number | null
  reviewRequestProvider?: 'gitlab' | 'github' | string
  status: string
  createdAt: string
  updatedAt: string
}

export interface DecisionTraceFileDecision {
  path: string
  why: string[]
  evidence: Array<{ source: string; summary: string; detail?: string }>
  confidence: number
  rejectedAlternatives: string[]
  role: string
}

export interface DecisionTracePayload {
  reasoningSummary: string
  overallConfidence: number
  fileDecisions: DecisionTraceFileDecision[]
  rejectedAlternatives: string[]
  riskAssessment: {
    databaseImpact: string
    apiImpact: string
    uiImpact: string
    summary: string[]
  }
}
