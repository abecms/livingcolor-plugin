import { getFirebaseIdToken } from '@/services/firebase'
import { $firebaseActiveOrgId, $firebaseIdToken, setFirebaseIdToken } from '@/store/firebase-auth'
import { $apiProjectKey } from '@/store/project-api-context'

export const LIVINGCOLOR_CLOUD_API_URL =
  (import.meta.env.VITE_LC_CLOUD_API_URL as string | undefined)?.replace(/\/$/, '') ||
  'https://api-livingcolor.visualq.ai'

function hermesPluginSdk(): { fetchJSON: (path: string, init?: RequestInit) => Promise<unknown> } | null {
  const sdk = (window as { __HERMES_PLUGIN_SDK__?: { fetchJSON?: (path: string, init?: RequestInit) => Promise<unknown> } })
    .__HERMES_PLUGIN_SDK__
  if (!sdk?.fetchJSON) {
    return null
  }
  return sdk as { fetchJSON: (path: string, init?: RequestInit) => Promise<unknown> }
}

function runningInHermesDashboard(): boolean {
  if (typeof window === 'undefined') {
    return false
  }
  if (hermesPluginSdk()) {
    return true
  }
  const { hostname, port } = window.location
  const loopback = hostname === '127.0.0.1' || hostname === 'localhost'
  return loopback && port === '9119'
}

function attachHermesDashboardSessionHeader(headers: Record<string, string>): void {
  const token = (window as { __HERMES_SESSION_TOKEN__?: string }).__HERMES_SESSION_TOKEN__
  if (!token) {
    return
  }
  if (!headers['X-Hermes-Session-Token'] && !headers['X-LivingColor-Session-Token']) {
    headers['X-Hermes-Session-Token'] = token
  }
}

function resolveCloudRequestUrl(path: string): { url: string; viaHermesProxy: boolean } {
  const normalized = path.startsWith('/') ? path : `/${path}`
  if (runningInHermesDashboard()) {
    // Same-origin proxy — cloud API CORS does not allow 127.0.0.1:9119 directly.
    return { url: `/api/plugins/livingcolor/cloud${normalized}`, viaHermesProxy: true }
  }
  return { url: `${LIVINGCOLOR_CLOUD_API_URL}${normalized}`, viaHermesProxy: false }
}

export async function callCloudApi<T>(request: {
  path: string
  method?: string
  body?: unknown
  /** When true, skip Authorization even if a token is cached. */
  public?: boolean
}): Promise<T> {
  const { url, viaHermesProxy } = resolveCloudRequestUrl(request.path)

  const headers: Record<string, string> = {}

  if (!request.public) {
    const token = $firebaseIdToken.get() || (await getFirebaseIdToken())
    if (!token) {
      throw new Error('Firebase sign-in required for team API calls')
    }
    headers.Authorization = `Bearer ${token}`
  }

  const orgId = $firebaseActiveOrgId.get()
  if (orgId) {
    headers['X-LC-Org-Id'] = orgId
  }

  const projectKey = $apiProjectKey.get()
  if (projectKey) {
    headers['X-LC-Project-Key'] = projectKey
  }

  if (viaHermesProxy) {
    attachHermesDashboardSessionHeader(headers)
  }

  const init: RequestInit = { method: request.method ?? 'GET', headers }
  if (request.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(request.body)
  }

  const execute = async (): Promise<T> => {
    if (viaHermesProxy) {
      const sdk = hermesPluginSdk()
      if (sdk) {
        return (await sdk.fetchJSON(url, init)) as T
      }
      const response = await fetch(url, { ...init, credentials: 'include' })
      if (!response.ok) {
        const text = await response.text()
        throw new Error(`${response.status}: ${text}`)
      }
      return response.json() as Promise<T>
    }

    const response = await fetch(url, init)
    if (!response.ok) {
      const text = await response.text()
      throw new Error(`${response.status}: ${text}`)
    }
    return response.json() as Promise<T>
  }

  try {
    return await execute()
  } catch (error) {
    if (!request.public && isFirebaseTokenApiError(error)) {
      const fresh = await getFirebaseIdToken(true)
      if (fresh) {
        setFirebaseIdToken(fresh)
        headers.Authorization = `Bearer ${fresh}`
        init.headers = headers
        return execute()
      }
    }
    throw error
  }
}

function isFirebaseTokenApiError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false
  }
  if (!/\b(401|403)\b/.test(error.message)) {
    return false
  }
  const lower = error.message.toLowerCase()
  return (
    lower.includes('invalid firebase id token') ||
    lower.includes('missing firebase id token') ||
    lower.includes('email not verified') ||
    lower.includes('unauthorized')
  )
}
