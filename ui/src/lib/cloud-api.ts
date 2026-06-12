import { getFirebaseIdToken } from '@/services/firebase'
import { $firebaseActiveOrgId, $firebaseIdToken, setFirebaseIdToken } from '@/store/firebase-auth'
import { $apiProjectKey } from '@/store/project-api-context'

export const LIVINGCOLOR_CLOUD_API_URL =
  (import.meta.env.VITE_LC_CLOUD_API_URL as string | undefined)?.replace(/\/$/, '') ||
  'https://api-livingcolor.visualq.ai'

export async function callCloudApi<T>(request: {
  path: string
  method?: string
  body?: unknown
  /** When true, skip Authorization even if a token is cached. */
  public?: boolean
}): Promise<T> {
  const base = LIVINGCOLOR_CLOUD_API_URL
  const url = `${base}${request.path.startsWith('/') ? '' : '/'}${request.path}`

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

  const init: RequestInit = { method: request.method ?? 'GET', headers }
  if (request.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(request.body)
  }

  let response = await fetch(url, init)

  if (!request.public && (response.status === 401 || response.status === 403)) {
    const fresh = await getFirebaseIdToken(true)
    if (fresh) {
      setFirebaseIdToken(fresh)
      headers.Authorization = `Bearer ${fresh}`
      response = await fetch(url, { ...init, headers })
    }
  }

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`${response.status}: ${text}`)
  }

  return response.json() as Promise<T>
}
