/**
 * Replacement for agent-lc's callDesktopApi (Electron IPC + Firebase).
 * Routes everything through the Hermes dashboard SDK fetchJSON, which
 * handles auth in both loopback and gated modes. Path prefixes are
 * rewritten: /api/delivery/*, /api/jira/*, /api/firebase/* →
 * /api/plugins/livingcolor/*.
 */
import { getFirebaseIdToken } from '@/services/firebase'
import { $firebaseActiveOrgId, $firebaseIdToken, setFirebaseIdToken } from '@/store/firebase-auth'
import { $apiOrgId, $apiProjectKey, LOCAL_ORG_ID } from '@/store/project-api-context'

export interface LivingColorApiRequest {
  path: string
  method?: string
  body?: unknown
  timeoutMs?: number
}

function rewrite(path: string): string {
  return path
    .replace(/^\/api\/delivery\//, '/api/plugins/livingcolor/delivery/')
    .replace(/^\/api\/jira\//, '/api/plugins/livingcolor/jira/')
    .replace(/^\/api\/firebase\//, '/api/plugins/livingcolor/firebase/')
    .replace(/^\/api\/mcp\/servers\//, '/api/plugins/livingcolor/mcp/servers/')
    .replace(/^\/api\/mcp\/integrations\//, '/api/plugins/livingcolor/mcp/integrations/')
    .replace(/^\/api\/settings$/, '/api/plugins/livingcolor/delivery/plugin-settings')
}

function buildHeaders(init: RequestInit): Headers {
  const headers = new Headers(init.headers)
  const token = $firebaseIdToken.get()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
    const orgId = $firebaseActiveOrgId.get() || ($apiOrgId.get() !== LOCAL_ORG_ID ? $apiOrgId.get() : null)
    if (orgId) {
      headers.set('x-lc-org-id', orgId)
    }
  }
  const projectKey = $apiProjectKey.get()
  if (projectKey) {
    headers.set('x-lc-project-key', projectKey)
  }
  return headers
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
    lower.includes('email not verified')
  )
}

function withTimeout<T>(promise: Promise<T>, timeoutMs?: number): Promise<T> {
  if (!timeoutMs || timeoutMs <= 0) {
    return promise
  }
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      reject(new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`))
    }, timeoutMs)
    promise.then(
      value => {
        window.clearTimeout(timer)
        resolve(value)
      },
      error => {
        window.clearTimeout(timer)
        reject(error)
      }
    )
  })
}

export async function callDesktopApi<T>(request: LivingColorApiRequest): Promise<T> {
  const sdk = (window as any).__HERMES_PLUGIN_SDK__
  if (!sdk) {
    throw new Error('Hermes plugin SDK unavailable')
  }

  const execute = async () => {
    const init: RequestInit = { method: request.method ?? 'GET' }
    if (request.body !== undefined) {
      init.headers = { 'Content-Type': 'application/json' }
      init.body = JSON.stringify(request.body)
    }
    init.headers = buildHeaders(init)
    return sdk.fetchJSON(rewrite(request.path), init) as Promise<T>
  }

  const run = async () => withTimeout(execute(), request.timeoutMs)

  try {
    return await run()
  } catch (error) {
    if (!isFirebaseTokenApiError(error)) {
      throw error
    }
    const freshToken = await getFirebaseIdToken(true)
    if (!freshToken) {
      throw error
    }
    setFirebaseIdToken(freshToken)
    return run()
  }
}
