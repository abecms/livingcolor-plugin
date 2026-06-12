import { switchToLocalWorkspace } from '@/store/workspace-scope'

import type { FirebaseAuthContextValue } from '@/contexts/firebase-auth-context'

const LOCAL_FIREBASE_AUTH: FirebaseAuthContextValue = {
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
  return LOCAL_FIREBASE_AUTH
}
