import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useRef } from 'react'

import { flushPendingEvents, pingCloudHealth, reportReconcileConflicts } from '@/lib/team-sync'
import { $workspaceScope } from '@/store/workspace-scope'

export function useTeamSync(onCloudStatusChange?: (reachable: boolean) => void): {
  flushNow: () => Promise<void>
} {
  const scope = useStore($workspaceScope)
  const orgId = scope.mode === 'org' ? scope.orgId : null
  const flushingRef = useRef(false)

  const flushNow = useCallback(async () => {
    if (!orgId || flushingRef.current) {
      return
    }
    flushingRef.current = true
    try {
      const result = await flushPendingEvents(orgId)
      reportReconcileConflicts(result.conflicts)
    } finally {
      flushingRef.current = false
    }
  }, [orgId])

  useEffect(() => {
    if (!orgId) {
      onCloudStatusChange?.(true)
      return
    }

    let cancelled = false

    const checkCloud = async () => {
      const reachable = typeof navigator !== 'undefined' && navigator.onLine ? await pingCloudHealth() : false
      if (!cancelled) {
        onCloudStatusChange?.(reachable)
      }
      return reachable
    }

    const handleOnline = () => {
      void (async () => {
        const reachable = await checkCloud()
        if (reachable) {
          await flushNow()
        }
      })()
    }

    void checkCloud()
    window.addEventListener('online', handleOnline)

    const interval = window.setInterval(() => {
      void checkCloud()
    }, 30_000)

    return () => {
      cancelled = true
      window.removeEventListener('online', handleOnline)
      window.clearInterval(interval)
    }
  }, [flushNow, onCloudStatusChange, orgId])

  return { flushNow }
}
