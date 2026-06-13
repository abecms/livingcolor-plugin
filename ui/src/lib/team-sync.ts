import { callCloudApi } from '@/lib/cloud-api'
import { callDesktopApi } from '@/lib/desktop-api'
import { notify, notifyError } from '@/store/notifications'

export interface PendingCloudEvent {
  id: number
  orgId: string
  woId: string
  payload: Record<string, unknown>
  createdAt: string
}

export interface ReconcileConflict {
  woId: string
  serverVersion: string
  clientVersion: string
  localEventId?: number | string
}

export interface ReconcileResult {
  orgId: string
  accepted: Array<number | string>
  conflicts: ReconcileConflict[]
}

export async function fetchPendingEventsFromLocalApi(orgId: string): Promise<PendingCloudEvent[]> {
  const response = await callDesktopApi<{ orgId: string; events: PendingCloudEvent[] }>({
    path: `/api/delivery/cloud/pending-events?orgId=${encodeURIComponent(orgId)}`
  })
  return response.events ?? []
}

export async function markPendingEventsFlushed(ids: number[]): Promise<void> {
  if (!ids.length) {
    return
  }
  await callDesktopApi({
    path: '/api/delivery/cloud/pending-events/mark-flushed',
    method: 'POST',
    body: { ids }
  })
}

export async function flushPendingEvents(orgId: string): Promise<ReconcileResult> {
  const pending = await fetchPendingEventsFromLocalApi(orgId)
  if (!pending.length) {
    return { orgId, accepted: [], conflicts: [] }
  }
  const result = await callCloudApi<ReconcileResult>({
    path: `/v1/orgs/${encodeURIComponent(orgId)}/sync/reconcile`,
    method: 'POST',
    body: {
      events: pending.map(event => ({
        id: event.id,
        woId: event.woId,
        payload: event.payload
      }))
    }
  })
  const acceptedIds = result.accepted
    .map(item => Number(item))
    .filter(item => Number.isFinite(item) && item > 0)
  await markPendingEventsFlushed(acceptedIds)
  if (result.conflicts.length) {
    notify({
      kind: 'warning',
      message: `${result.conflicts.length} offline change(s) need manual review.`
    })
  }
  return result
}

export async function enqueuePendingCloudEvent(
  orgId: string,
  woId: string,
  payload: Record<string, unknown>
): Promise<number> {
  const response = await callDesktopApi<{ id: number }>({
    path: '/api/delivery/cloud/pending-events',
    method: 'POST',
    body: { orgId, woId, payload }
  })
  return response.id
}

export async function pingCloudHealth(): Promise<boolean> {
  try {
    await callCloudApi<{ status?: string }>({ path: '/v1/health', public: true })
    return true
  } catch {
    return false
  }
}

export function reportReconcileConflicts(conflicts: ReconcileConflict[]): void {
  if (!conflicts.length) {
    return
  }
  const summary = conflicts.map(item => item.woId).join(', ')
  notifyError(new Error('Reconcile conflicts'), `Cloud state diverged for: ${summary}`)
}
