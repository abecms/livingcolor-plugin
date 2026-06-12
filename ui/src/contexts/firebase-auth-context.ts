import { createContext } from 'react'

import type { FirebaseOrgMember, FirebaseOrgSummary } from '@/lib/firebase-session'

export type FirebaseAuthStatus = 'disabled' | 'loading' | 'signed-out' | 'signed-in'

export interface FirebaseAuthUser {
  uid: string
  email?: string | null
  displayName?: string | null
}

export interface FirebaseAuthContextValue {
  enabled: boolean
  status: FirebaseAuthStatus
  user: FirebaseAuthUser | null
  activeOrgId: string | null
  organizations: FirebaseOrgSummary[]
  activeOrg: FirebaseOrgSummary | null
  signOut: () => Promise<void>
  refreshSession: () => Promise<void>
  switchToLocalProjects: () => void
  switchOrganization: (orgId: string) => Promise<void>
  createTeam: (name: string) => Promise<FirebaseOrgSummary>
  inviteMember: (email: string, role?: 'admin' | 'member') => Promise<void>
  removeMember: (memberUid: string) => Promise<void>
  reloadOrganizations: () => Promise<void>
}

export const FirebaseAuthReactContext = createContext<FirebaseAuthContextValue | null>(null)

export type { FirebaseOrgMember, FirebaseOrgSummary }
