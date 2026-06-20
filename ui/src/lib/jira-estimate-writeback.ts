import type { GateDecisionResult } from '@/lib/delivery'

export function formatJiraEstimateWritebackNotice(
  jiraKey: string,
  writeback: GateDecisionResult['jiraEstimateWriteback']
): string | null {
  if (!writeback) {
    return null
  }
  if (writeback.written) {
    const estimate = writeback.estimate ? ` (${writeback.estimate})` : ''
    if (writeback.overwritten) {
      return `Jira original estimate updated on ${jiraKey}${estimate}.`
    }
    return `Jira original estimate set on ${jiraKey}${estimate}.`
  }
  if (writeback.reason === 'shadow_mode') {
    return null
  }
  if (writeback.reason === 'invoker_not_configured') {
    return `Gate approved, but Jira estimate write-back is not configured on this server.`
  }
  if (writeback.reason === 'already_set' && writeback.written === false) {
    return `Gate approved. Jira already had an original estimate on ${jiraKey}.`
  }
  if (writeback.reason) {
    return `Gate approved, but Jira estimate was not updated (${writeback.reason}).`
  }
  return null
}
