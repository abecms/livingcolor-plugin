import { hermesBasePath } from '@/lib/hermes-app-path'

export const LIVINGCOLOR_PM_PROFILE = 'livingcolor-pm'

export interface HermesProfileSession {
  id: string
  title?: string | null
  message_count?: number
  last_active?: number
  profile?: string
}

export interface HermesPluginSdk {
  sdkVersion?: string
  api?: {
    getSessions?: (limit?: number, offset?: number) => Promise<{
      sessions?: Array<{
        id: string
        title?: string | null
        message_count?: number
        last_active?: number
      }>
    }>
    getSessionLatestDescendant?: (id: string) => Promise<{ session_id: string }>
    renameSession?: (id: string, title: string) => Promise<unknown>
  }
  buildWsUrl?: (path: string, params?: Record<string, string>) => Promise<string>
  buildWsAuthParam?: () => Promise<[string, string]>
  fetchJSON?: <T = unknown>(url: string, init?: RequestInit) => Promise<T>
}

export function getHermesPluginSdk(): HermesPluginSdk | null {
  if (typeof window === 'undefined') {
    return null
  }

  return (window as Window & { __HERMES_PLUGIN_SDK__?: HermesPluginSdk }).__HERMES_PLUGIN_SDK__ ?? null
}

export async function fetchLivingColorProfileSessions(limit = 50): Promise<HermesProfileSession[]> {
  const sdk = getHermesPluginSdk()
  const query = `/api/profiles/sessions?profile=${encodeURIComponent(LIVINGCOLOR_PM_PROFILE)}&limit=${limit}&min_messages=0&archived=exclude&order=recent`

  if (sdk?.fetchJSON) {
    const response = await sdk.fetchJSON<{ sessions?: HermesProfileSession[] }>(query)
    return response.sessions ?? []
  }

  const base = hermesBasePath()
  const response = await fetch(`${base}${query}`, { credentials: 'include' })
  if (!response.ok) {
    return []
  }

  const payload = (await response.json()) as { sessions?: HermesProfileSession[] }
  return payload.sessions ?? []
}

export async function buildHermesPtyWebSocketUrl(options: {
  channel: string
  livingcolorProjectKey?: string | null
  resumeSessionId?: string | null
  profile?: string
}): Promise<string> {
  const sdk = getHermesPluginSdk()
  const params: Record<string, string> = { channel: options.channel }
  const projectKey = options.livingcolorProjectKey?.trim().toUpperCase()
  if (projectKey) {
    params.livingcolor_project_key = projectKey
    params.profile = options.profile ?? LIVINGCOLOR_PM_PROFILE
  }
  if (options.resumeSessionId) {
    params.resume = options.resumeSessionId
  }
  if (options.profile) {
    params.profile = options.profile
  }

  if (sdk?.buildWsUrl) {
    return sdk.buildWsUrl('/api/pty', params)
  }

  const authParam = sdk?.buildWsAuthParam
    ? await sdk.buildWsAuthParam()
    : (['token', (window as Window & { __HERMES_SESSION_TOKEN__?: string }).__HERMES_SESSION_TOKEN__ ?? ''] as [
        string,
        string,
      ])

  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const qs = new URLSearchParams({ [authParam[0]]: authParam[1], channel: options.channel })
  if (projectKey) {
    qs.set('livingcolor_project_key', projectKey)
    qs.set('profile', options.profile ?? LIVINGCOLOR_PM_PROFILE)
  }
  if (options.resumeSessionId) {
    qs.set('resume', options.resumeSessionId)
  }
  if (options.profile) {
    qs.set('profile', options.profile)
  }

  const base = hermesBasePath()
  return `${proto}//${window.location.host}${base}/api/pty?${qs.toString()}`
}
