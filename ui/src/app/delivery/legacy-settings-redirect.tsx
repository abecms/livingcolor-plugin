import { useEffect } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'

import { buildHermesAppPath, HERMES_MCP_SETTINGS_PATH } from '@/lib/hermes-app-path'

/** Legacy `/livingcolor/settings?tab=mcp` bookmarks → Hermes MCP page. */
export function LegacySettingsRedirect() {
  const [params] = useSearchParams()
  const tab = params.get('tab')

  useEffect(() => {
    if (tab === 'mcp') {
      window.location.assign(buildHermesAppPath(HERMES_MCP_SETTINGS_PATH))
    }
  }, [tab])

  if (tab === 'mcp') {
    return null
  }

  return <Navigate replace to="/" />
}
