/** Firebase client config exposed to the LivingColor plugin UI. */

import { LIVINGCOLOR_CLOUD_FIREBASE_CONFIG } from '@/lib/firebase-config.defaults'
import { fetchFirebaseClientConfig } from '@/lib/firebase-session'

export interface FirebaseWebConfig {
  apiKey: string
  authDomain: string
  projectId: string
  storageBucket: string
  messagingSenderId: string
  appId: string
}

export type FirebaseConfigSource = 'vite-env' | 'backend' | 'cloud-defaults' | 'none'

let _resolvedConfig: FirebaseWebConfig | null | undefined
let _resolvedSource: FirebaseConfigSource = 'none'
let _resolvePromise: Promise<FirebaseWebConfig | null> | null = null

function readViteFirebaseWebConfig(): FirebaseWebConfig | null {
  if (!import.meta.env.VITE_FIREBASE_API_KEY || !import.meta.env.VITE_FIREBASE_PROJECT_ID) {
    return null
  }
  return {
    apiKey: String(import.meta.env.VITE_FIREBASE_API_KEY),
    authDomain: String(
      import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || `${import.meta.env.VITE_FIREBASE_PROJECT_ID}.firebaseapp.com`
    ),
    projectId: String(import.meta.env.VITE_FIREBASE_PROJECT_ID),
    storageBucket: String(import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || ''),
    messagingSenderId: String(import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || ''),
    appId: String(import.meta.env.VITE_FIREBASE_APP_ID || '')
  }
}

function normalizeBackendConfig(config: Record<string, string> | null | undefined): FirebaseWebConfig | null {
  if (!config?.apiKey || !config?.projectId) {
    return null
  }
  return {
    apiKey: config.apiKey,
    authDomain: config.authDomain || `${config.projectId}.firebaseapp.com`,
    projectId: config.projectId,
    storageBucket: config.storageBucket || '',
    messagingSenderId: config.messagingSenderId || '',
    appId: config.appId || ''
  }
}

export function getFirebaseConfigSource(): FirebaseConfigSource {
  return _resolvedSource
}

export function getCachedFirebaseWebConfig(): FirebaseWebConfig | null {
  if (_resolvedConfig === undefined) {
    return readViteFirebaseWebConfig()
  }
  return _resolvedConfig
}

/** Sync check — true once Vite env or a prior async resolve found config. */
export function firebaseClientConfigured(): boolean {
  return getCachedFirebaseWebConfig() !== null
}

/** @deprecated Prefer resolveFirebaseWebConfig() for packaged builds. */
export function readFirebaseWebConfig(): FirebaseWebConfig | null {
  return getCachedFirebaseWebConfig()
}

/**
 * Resolve Firebase web config for the Hermes plugin tab.
 *
 * Order:
 * 1. VITE_* (local dev override, gitignored .env.local)
 * 2. LivingColor backend `/api/firebase/client-config` (requires admin configured)
 * 3. Committed cloud defaults when backend reports enabled but omits fields
 */
export async function resolveFirebaseWebConfig(): Promise<FirebaseWebConfig | null> {
  if (_resolvedConfig !== undefined) {
    return _resolvedConfig
  }
  if (_resolvePromise) {
    return _resolvePromise
  }

  _resolvePromise = (async () => {
    const fromVite = readViteFirebaseWebConfig()
    if (fromVite) {
      _resolvedConfig = fromVite
      _resolvedSource = 'vite-env'
      return fromVite
    }

    try {
      const payload = await fetchFirebaseClientConfig()
      if (!payload.enabled) {
        _resolvedConfig = null
        _resolvedSource = 'none'
        return null
      }
      const fromBackend = normalizeBackendConfig(payload.config)
      if (fromBackend) {
        _resolvedConfig = fromBackend
        _resolvedSource = 'backend'
        return fromBackend
      }
      _resolvedConfig = LIVINGCOLOR_CLOUD_FIREBASE_CONFIG
      _resolvedSource = 'cloud-defaults'
      return LIVINGCOLOR_CLOUD_FIREBASE_CONFIG
    } catch {
      _resolvedConfig = null
      _resolvedSource = 'none'
      return null
    }
  })()

  return _resolvePromise
}

export function resetFirebaseWebConfigCache(): void {
  _resolvedConfig = undefined
  _resolvedSource = 'none'
  _resolvePromise = null
}
