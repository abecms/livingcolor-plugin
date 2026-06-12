import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { acquireWorkOrderLock, releaseWorkOrderLock } from '@/lib/work-order-lock-api'
import { getFirebaseAuth } from '@/services/firebase'
import { subscribeWorkOrderLock, type WorkOrderLockDoc } from '@/services/firebase-firestore'
import { $workspaceScope } from '@/store/workspace-scope'

export interface WorkOrderLockState {
  orgId: string | null
  lock: WorkOrderLockDoc | null
  canWrite: boolean
  holderEmail: string | null
  loading: boolean
  acquire: () => Promise<boolean>
  release: () => Promise<void>
  lockMessage: string | null
}

export function useWorkOrderLock(workOrderId: string | null | undefined): WorkOrderLockState {
  const scope = useStore($workspaceScope)
  const orgId = scope.mode === 'org' ? scope.orgId : null
  const [lock, setLock] = useState<WorkOrderLockDoc | null>(null)
  const [currentUid, setCurrentUid] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!orgId || !workOrderId) {
      setLock(null)
      setCurrentUid(null)
      return
    }

    let unsubscribe: (() => void) | undefined
    let cancelled = false

    void (async () => {
      await getFirebaseAuth().authStateReady()
      if (cancelled) {
        return
      }
      setCurrentUid(getFirebaseAuth().currentUser?.uid ?? null)
      unsubscribe = await subscribeWorkOrderLock(orgId, workOrderId, next => {
        if (!cancelled) {
          setLock(next)
        }
      })
    })()

    return () => {
      cancelled = true
      unsubscribe?.()
    }
  }, [orgId, workOrderId])

  const canWrite = useMemo(() => {
    if (!orgId) {
      return true
    }
    if (!lock?.holderUid) {
      return true
    }
    return Boolean(currentUid && lock.holderUid === currentUid)
  }, [orgId, lock, currentUid])

  const holderEmail = lock?.holderEmail?.trim() || null

  const lockMessage = useMemo(() => {
    if (!orgId || canWrite) {
      return null
    }
    if (holderEmail) {
      return `Locked by ${holderEmail}`
    }
    return 'Locked by another team member'
  }, [orgId, canWrite, holderEmail])

  const acquire = useCallback(async () => {
    if (!orgId || !workOrderId) {
      return true
    }
    setLoading(true)
    try {
      await acquireWorkOrderLock(orgId, workOrderId)
      return true
    } catch {
      return false
    } finally {
      setLoading(false)
    }
  }, [orgId, workOrderId])

  const release = useCallback(async () => {
    if (!orgId || !workOrderId || !canWrite) {
      return
    }
    setLoading(true)
    try {
      await releaseWorkOrderLock(orgId, workOrderId)
    } finally {
      setLoading(false)
    }
  }, [orgId, workOrderId, canWrite])

  return {
    orgId,
    lock,
    canWrite,
    holderEmail,
    loading,
    acquire,
    release,
    lockMessage
  }
}
