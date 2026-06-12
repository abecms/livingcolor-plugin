export interface AnalysisPlanGatePayload {
  nodeId?: string
  ticketUnderstanding?: string
  jiraContextUsed?: Record<string, unknown>
  targetRepo?: string
  implementationPlan?: string
  likelyImpactedFiles?: string[]
  risks?: string[]
  confidenceLevel?: number
}

export function asAnalysisPlanPayload(payload: Record<string, unknown>): AnalysisPlanGatePayload {
  return payload as AnalysisPlanGatePayload
}
