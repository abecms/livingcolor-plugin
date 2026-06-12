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

export function formatWorkOrderStage(stage: string): string {
  return WORK_ORDER_STAGE_LABELS[stage] ?? stage.replaceAll('_', ' ')
}

export function formatGraphNodeLabel(node: GraphNode): string {
  if (node.nodeType === 'development') {
    const phase = String(node.payload?.developerPhase ?? '')
    if (phase === 'merge_conflict_resolution') {
      return WORK_ORDER_STAGE_LABELS.merge_conflict_resolution
    }
  }
  return GRAPH_NODE_LABELS[node.nodeType] ?? node.nodeType.replaceAll('_', ' ')
}
