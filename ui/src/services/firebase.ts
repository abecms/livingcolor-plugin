/** Local-mode stub — Firebase is not available in the Hermes plugin dashboard tab. */

export async function getFirebaseIdToken(_forceRefresh = false): Promise<string | null> {
  return null
}

export function getFirebaseAuth(): never {
  throw new Error('Firebase is not available in the LivingColor plugin')
}

export function isFirebaseEnabled(): boolean {
  return false
}

export async function initializeFirebaseClient(): Promise<boolean> {
  return false
}

export async function signInWithGoogle(): Promise<never> {
  throw new Error('Firebase is not available in the LivingColor plugin')
}

export async function signInWithEmail(_email: string, _password: string): Promise<never> {
  throw new Error('Firebase is not available in the LivingColor plugin')
}

export async function registerWithEmail(_email: string, _password: string): Promise<never> {
  throw new Error('Firebase is not available in the LivingColor plugin')
}

export async function firebaseLogout(): Promise<void> {
  return undefined
}
