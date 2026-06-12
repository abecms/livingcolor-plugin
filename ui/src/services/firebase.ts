import { getApps, initializeApp, type FirebaseApp } from 'firebase/app'
import {
  browserLocalPersistence,
  browserPopupRedirectResolver,
  createUserWithEmailAndPassword,
  getAuth,
  getRedirectResult,
  GoogleAuthProvider,
  initializeAuth,
  onAuthStateChanged,
  sendEmailVerification,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  type Auth,
  type User
} from 'firebase/auth'

import { getCachedFirebaseWebConfig, resolveFirebaseWebConfig } from '@/lib/firebase-config'

let _app: FirebaseApp | undefined
let _auth: Auth | undefined
let _initPromise: Promise<boolean> | null = null
let _redirectHandled = false

function isElectronShell(): boolean {
  return false
}

async function waitForAuthUser(auth: Auth, timeoutMs = 15_000): Promise<User> {
  await auth.authStateReady()
  if (auth.currentUser) {
    return auth.currentUser
  }

  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      unsubscribe()
      reject(new Error('Google sign-in completed but user session was not detected'))
    }, timeoutMs)

    const unsubscribe = onAuthStateChanged(auth, user => {
      if (!user) {
        return
      }
      window.clearTimeout(timeout)
      unsubscribe()
      resolve(user)
    })
  })
}

async function ensureFirebaseReady(): Promise<boolean> {
  if (_initPromise) {
    return _initPromise
  }

  _initPromise = (async () => {
    const config = await resolveFirebaseWebConfig()
    if (!config) {
      return false
    }
    if (!_app) {
      _app = getApps().length === 0 ? initializeApp(config) : getApps()[0]!
    }
    if (!_auth) {
      try {
        _auth = initializeAuth(_app, {
          persistence: browserLocalPersistence,
          popupRedirectResolver: browserPopupRedirectResolver
        })
      } catch {
        _auth = getAuth(_app)
      }
    }
    await completePendingGoogleRedirect()
    return true
  })()

  return _initPromise
}

async function completePendingGoogleRedirect(): Promise<User | null> {
  if (_redirectHandled || !_auth || isElectronShell()) {
    return null
  }
  _redirectHandled = true
  try {
    const result = await getRedirectResult(_auth, browserPopupRedirectResolver)
    return result?.user ?? null
  } catch {
    return null
  }
}

function getFirebaseApp(): FirebaseApp {
  const config = getCachedFirebaseWebConfig()
  if (!config || !_app) {
    throw new Error('Firebase client is not initialized yet')
  }
  return _app
}

export function getFirebaseAuth(): Auth {
  if (!_auth) {
    _auth = getAuth(getFirebaseApp())
  }
  return _auth
}

export function isFirebaseEnabled(): boolean {
  return getCachedFirebaseWebConfig() !== null
}

export async function initializeFirebaseClient(): Promise<boolean> {
  return ensureFirebaseReady()
}

export async function signInWithGoogle(): Promise<User> {
  await ensureFirebaseReady()
  const auth = getFirebaseAuth()

  const provider = new GoogleAuthProvider()
  provider.setCustomParameters({ prompt: 'select_account' })
  const popupResult = await signInWithPopup(auth, provider, browserPopupRedirectResolver)
  return popupResult.user
}

export async function signInWithEmail(email: string, password: string): Promise<User> {
  await ensureFirebaseReady()
  const result = await signInWithEmailAndPassword(getFirebaseAuth(), email, password)
  return result.user
}

export async function registerWithEmail(email: string, password: string): Promise<User> {
  await ensureFirebaseReady()
  const result = await createUserWithEmailAndPassword(getFirebaseAuth(), email, password)
  await sendEmailVerification(result.user)
  return result.user
}

export async function firebaseLogout(): Promise<void> {
  if (!_auth) {
    return
  }
  await signOut(getFirebaseAuth())
}

export async function getFirebaseIdToken(forceRefresh = false): Promise<string | null> {
  await ensureFirebaseReady()
  const user = getFirebaseAuth().currentUser
  if (!user) {
    return null
  }
  return user.getIdToken(forceRefresh)
}
