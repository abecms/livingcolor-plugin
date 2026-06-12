const FIREBASE_SESSION_CACHE_KEY = 'livingcolor.firebase.session'

export interface CachedFirebaseSession {
  uid: string
  email: string
  activeOrgId: string | null
}

export function readCachedFirebaseSession(): CachedFirebaseSession | null {
  if (typeof window === 'undefined') {
    return null
  }
  try {
    const raw = window.localStorage.getItem(FIREBASE_SESSION_CACHE_KEY)
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as CachedFirebaseSession
    if (!parsed?.uid) {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function writeCachedFirebaseSession(session: CachedFirebaseSession): void {
  if (typeof window === 'undefined') {
    return
  }
  try {
    window.localStorage.setItem(FIREBASE_SESSION_CACHE_KEY, JSON.stringify(session))
  } catch {
    // ignore quota / privacy mode
  }
}

export function clearCachedFirebaseSession(): void {
  if (typeof window === 'undefined') {
    return
  }
  try {
    window.localStorage.removeItem(FIREBASE_SESSION_CACHE_KEY)
  } catch {
    // ignore
  }
}
