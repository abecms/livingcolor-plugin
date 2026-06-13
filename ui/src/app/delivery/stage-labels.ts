import {
  formatGraphNodeTypeLabel,
  formatWorkOrderStageLabel,
  type ReviewRequestProvider
} from './review-request-labels'
import type { GraphNode, WorkOrderStage } from './types'

const WORK_ORDER_STAGE_LABELS: Record<WorkOrderStage | string, string> = {
  intake: 'Intake',
  analysis_review: 'Analysis review',
  clarification: 'Clarification',
  development: 'Development',
  merge_conflict_resolution: 'Merge conflict resolution',
  code_review: 'Code review',
  mr_draft: 'MR draft',
  awaiting_next_phase: 'Awaiting next phase',
  mr_review: 'MR review',
  mr_publication: 'Publication GitLab',
  jira_review: 'Jira review',
  completed: 'Completed'
}

const GRAPH_NODE_LABELS: Record<string, string> = {
  implementation_plan: 'Analysis & plan',
  development: 'Development',
  qa_validation: 'QA validation',
  mr_creation: 'MR draft',
  jira_update: 'Jira update'
}

const PROVIDER_AWARE_STAGES = new Set(['mr_draft', 'mr_review', 'mr_publication'])

export function formatWorkOrderStage(stage: string, provider?: ReviewRequestProvider): string {
  if (provider && PROVIDER_AWARE_STAGES.has(stage)) {
    return formatWorkOrderStageLabel(stage, provider)
  }
  return WORK_ORDER_STAGE_LABELS[stage] ?? stage.replaceAll('_', ' ')
}

export function formatGraphNodeLabel(node: GraphNode, provider?: ReviewRequestProvider): string {
  if (node.nodeType === 'development') {
    const phase = String(node.payload?.developerPhase ?? '')
    if (phase === 'merge_conflict_resolution') {
      return WORK_ORDER_STAGE_LABELS.merge_conflict_resolution
    }
  }
  if (provider && node.nodeType === 'mr_creation') {
    return formatGraphNodeTypeLabel(node.nodeType, provider)
  }
  return GRAPH_NODE_LABELS[node.nodeType] ?? node.nodeType.replaceAll('_', ' ')
}
