import { useStore } from '@nanostores/react'
import { useEffect, useState } from 'react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { useTeamSync } from '@/hooks/use-team-sync'
import { $workspaceScope } from '@/store/workspace-scope'

export function OfflineBanner() {
  const scope = useStore($workspaceScope)
  const [cloudReachable, setCloudReachable] = useState(true)
  const [browserOnline, setBrowserOnline] = useState(
    typeof navigator === 'undefined' ? true : navigator.onLine
  )

  useTeamSync(reachable => {
    setCloudReachable(reachable)
  })

  useEffect(() => {
    const handleOffline = () => setBrowserOnline(false)
    const handleOnline = () => setBrowserOnline(true)
    window.addEventListener('offline', handleOffline)
    window.addEventListener('online', handleOnline)
    return () => {
      window.removeEventListener('offline', handleOffline)
      window.removeEventListener('online', handleOnline)
    }
  }, [])

  if (scope.mode !== 'org') {
    return null
  }

  if (browserOnline && cloudReachable) {
    return null
  }

  return (
    <Alert className="rounded-none border-x-0 border-t-0" variant="destructive">
      <AlertTitle>Offline — read only</AlertTitle>
      <AlertDescription>
        Team cloud sync is unavailable. You can review cached delivery state, but work-order changes are
        disabled until connectivity returns.
      </AlertDescription>
    </Alert>
  )
}
