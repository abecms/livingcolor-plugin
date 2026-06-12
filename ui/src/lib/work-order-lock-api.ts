import { callCloudApi } from '@/lib/cloud-api'
import type { WorkOrderLockDoc } from '@/services/firebase-firestore'

export interface WorkOrderLockResponse {
  orgId: string
  workOrderId: string
  lock?: WorkOrderLockDoc
  released?: boolean
}

export function acquireWorkOrderLock(
  orgId: string,
  workOrderId: string,
  sessionId?: string
): Promise<WorkOrderLockResponse> {
  return callCloudApi({
    path: `/v1/orgs/${encodeURIComponent(orgId)}/work-orders/${encodeURIComponent(workOrderId)}/lock`,
    method: 'POST',
    body: sessionId ? { sessionId } : {}
  })
}

export function releaseWorkOrderLock(orgId: string, workOrderId: string): Promise<WorkOrderLockResponse> {
  return callCloudApi({
    path: `/v1/orgs/${encodeURIComponent(orgId)}/work-orders/${encodeURIComponent(workOrderId)}/lock`,
    method: 'DELETE'
  })
}
