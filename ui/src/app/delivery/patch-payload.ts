export interface CodeReviewGatePayload {
  nodeId?: string
  summary?: string
  filesModified?: string[]
  filesCreated?: string[]
  patchStats?: Record<string, number>
  diffPreview?: string
  confidence?: number
  risks?: string[]
  implementationPlan?: string
  likelyImpactedFiles?: string[]
  patchArtifactPath?: string
  reportArtifactPath?: string
}

export function asCodeReviewPayload(payload: Record<string, unknown>): CodeReviewGatePayload {
  return payload as CodeReviewGatePayload
}
