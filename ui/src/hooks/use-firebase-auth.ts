import { useContext } from 'react'

import {
  FirebaseAuthReactContext,
  type FirebaseAuthContextValue
} from '@/contexts/firebase-auth-context'

export function useFirebaseAuth(): FirebaseAuthContextValue {
  const ctx = useContext(FirebaseAuthReactContext)
  if (!ctx) {
    throw new Error('useFirebaseAuth must be used within FirebaseAuthProvider')
  }
  return ctx
}
