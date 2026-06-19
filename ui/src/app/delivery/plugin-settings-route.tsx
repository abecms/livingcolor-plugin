import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'

import { buildHermesAppPath, HERMES_MCP_SETTINGS_PATH } from '@/lib/hermes-app-path'

import { PluginSettingsView } from './plugin-settings-view'

/** `/livingcolor/settings` — global plugin settings; `?tab=mcp` keeps legacy Hermes redirect. */
export function PluginSettingsRoute() {
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

  return <PluginSettingsView />
}
