import { useContext } from 'react'

import {
  FirebaseAuthReactContext,
  type FirebaseAuthContextValue
} from '@/contexts/firebase-auth-context'
import { switchToLocalWorkspace } from '@/store/workspace-scope'

const DISABLED_FIREBASE_AUTH: FirebaseAuthContextValue = {
  enabled: false,
  status: 'disabled',
  user: null,
  activeOrgId: null,
  organizations: [],
  activeOrg: null,
  signOut: async () => undefined,
  refreshSession: async () => undefined,
  switchToLocalProjects: () => switchToLocalWorkspace(),
  switchOrganization: async () => undefined,
  createTeam: async () => {
    throw new Error('Firebase auth is not enabled')
  },
  inviteMember: async () => undefined,
  removeMember: async () => undefined,
  reloadOrganizations: async () => undefined
}

export function useFirebaseAuth(): FirebaseAuthContextValue {
  const ctx = useContext(FirebaseAuthReactContext)
  if (!ctx) {
    if (import.meta.env.DEV) {
      return DISABLED_FIREBASE_AUTH
    }
    throw new Error('useFirebaseAuth must be used within FirebaseAuthProvider')
  }
  return ctx
}
