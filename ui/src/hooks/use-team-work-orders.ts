import { useStore } from '@nanostores/react'
import { useEffect, useMemo, useState } from 'react'

import type { DeliveryGate, GraphNode, WorkOrder, WorkOrderStage, WorkOrderStatus } from '@/app/delivery/types'
import { subscribeTeamWorkOrders } from '@/services/firebase-firestore'
import { $workspaceScope } from '@/store/workspace-scope'

function mapFirestoreWorkOrder(id: string, data: Record<string, unknown>): WorkOrder {
  return {
    id,
    jiraKey: String(data.jiraKey ?? ''),
    readinessId: (data.readinessId as string | null | undefined) ?? null,
    title: String(data.title ?? id),
    description: String(data.description ?? ''),
    priority: String(data.priority ?? 'medium'),
    status: (String(data.status ?? 'intake') as WorkOrderStatus) || 'intake',
    currentStage: (String(data.currentStage ?? 'intake') as WorkOrderStage) || 'intake',
    confidence: Number(data.confidence ?? 0),
    createdAt: String(data.createdAt ?? ''),
    updatedAt: String(data.updatedAt ?? ''),
    graphNodes: Array.isArray(data.graphNodes) ? (data.graphNodes as GraphNode[]) : undefined,
    gates: Array.isArray(data.gates) ? (data.gates as DeliveryGate[]) : undefined
  }
}

function mergeWorkOrders(remote: WorkOrder[], local: WorkOrder[]): WorkOrder[] {
  const merged = new Map<string, WorkOrder>()
  for (const workOrder of local) {
    merged.set(workOrder.id, workOrder)
  }
  for (const workOrder of remote) {
    const existing = merged.get(workOrder.id)
    if (!existing) {
      merged.set(workOrder.id, workOrder)
      continue
    }
    const remoteIsNewer = workOrder.updatedAt >= existing.updatedAt
    merged.set(workOrder.id, {
      ...existing,
      ...workOrder,
      graphNodes: remoteIsNewer ? workOrder.graphNodes ?? existing.graphNodes : existing.graphNodes ?? workOrder.graphNodes,
      gates: remoteIsNewer ? workOrder.gates ?? existing.gates : existing.gates ?? workOrder.gates
    })
  }
  return [...merged.values()]
}

export interface TeamWorkOrdersState {
  workOrders: WorkOrder[]
  loading: boolean
  source: 'local' | 'merged'
}

export function useTeamWorkOrders(localWorkOrders: WorkOrder[]): TeamWorkOrdersState {
  const scope = useStore($workspaceScope)
  const orgId = scope.mode === 'org' ? scope.orgId : null
  const [remoteWorkOrders, setRemoteWorkOrders] = useState<WorkOrder[]>([])
  const [loading, setLoading] = useState(Boolean(orgId))

  useEffect(() => {
    if (!orgId) {
      setRemoteWorkOrders([])
      setLoading(false)
      return
    }

    let unsubscribe: (() => void) | undefined
    let cancelled = false
    setLoading(true)

    void subscribeTeamWorkOrders(orgId, items => {
      if (cancelled) {
        return
      }
      setRemoteWorkOrders(items.map(item => mapFirestoreWorkOrder(item.id, item.data)))
      setLoading(false)
    })
      .then(unsub => {
        if (cancelled) {
          unsub()
          return
        }
        unsubscribe = unsub
      })
      .catch(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
      unsubscribe?.()
    }
  }, [orgId])

  const workOrders = useMemo(() => {
    if (!orgId) {
      return localWorkOrders
    }
    return mergeWorkOrders(remoteWorkOrders, localWorkOrders)
  }, [localWorkOrders, orgId, remoteWorkOrders])

  return {
    workOrders,
    loading,
    source: orgId ? 'merged' : 'local'
  }
}
