import { onAuthStateChanged, type User } from 'firebase/auth'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { writeStoredJiraProjectKey } from '@/lib/jira-project-storage'
import {
  clearCachedFirebaseSession,
  readCachedFirebaseSession,
  writeCachedFirebaseSession
} from '@/lib/firebase-session-cache'
import {
  bootstrapFirebaseSession,
  createFirebaseTeamOrg,
  fetchFirebaseMe,
  fetchFirebasePreferences,
  inviteOrgMember,
  removeOrgMember,
  setFirebaseActiveOrg,
  type FirebaseOrgSummary
} from '@/lib/firebase-session'
import {
  firebaseLogout,
  getFirebaseAuth,
  getFirebaseIdToken,
  initializeFirebaseClient
} from '@/services/firebase'
import { setFirebaseActiveOrgId, setFirebaseIdToken } from '@/store/firebase-auth'
import { bumpProjectConfigRevision } from '@/store/project-config'
import {
  $workspaceScope,
  applyWorkspaceScope,
  hydrateWorkspaceScopeFromStorage,
  isLocalWorkspaceScope,
  readStoredWorkspaceScope,
  switchToLocalWorkspace,
  switchToOrgWorkspace,
  type WorkspaceScope
} from '@/store/workspace-scope'

import { FirebaseAuthReactContext, type FirebaseAuthContextValue } from './firebase-auth-context'

const TOKEN_REFRESH_MS = 50 * 60 * 1000

async function applyOrgPreferences(): Promise<void> {
  try {
    const prefs = await fetchFirebasePreferences()
    const projectKey = prefs.preferences.selectedJiraProjectKey?.trim()
    writeStoredJiraProjectKey(projectKey || null)
    bumpProjectConfigRevision()
  } catch {
    // Preferences sync is best-effort when the backend is offline.
  }
}

function resolveWorkspaceScope(
  bootstrapOrgId: string,
  organizations: FirebaseOrgSummary[]
): { scope: WorkspaceScope; orgId: string | null } {
  const stored = readStoredWorkspaceScope()
  if (stored?.mode === 'local') {
    applyWorkspaceScope({ mode: 'local' })
    return { scope: { mode: 'local' }, orgId: null }
  }
  if (stored?.mode === 'org' && organizations.some(org => org.id === stored.orgId)) {
    applyWorkspaceScope(stored)
    return { scope: stored, orgId: stored.orgId }
  }
  const orgId = bootstrapOrgId
  applyWorkspaceScope({ mode: 'org', orgId })
  return { scope: { mode: 'org', orgId }, orgId }
}

async function hydrateServerSession(user: User): Promise<{
  orgId: string | null
  organizations: FirebaseOrgSummary[]
}> {
  const token = await user.getIdToken()
  setFirebaseIdToken(token)
  hydrateWorkspaceScopeFromStorage()
  const bootstrap = await bootstrapFirebaseSession()
  const resolved = resolveWorkspaceScope(bootstrap.user.activeOrgId, bootstrap.organizations)
  if (!isLocalWorkspaceScope(resolved.scope) && resolved.orgId) {
    writeCachedFirebaseSession({
      uid: user.uid,
      email: user.email || '',
      activeOrgId: resolved.orgId
    })
    await applyOrgPreferences()
  }
  return { orgId: resolved.orgId, organizations: bootstrap.organizations }
}

function restoreCachedSession(user: User): {
  orgId: string | null
  organizations: FirebaseOrgSummary[]
} {
  const cached = readCachedFirebaseSession()
  const orgId = cached?.uid === user.uid ? cached.activeOrgId : null
  if (orgId) {
    setFirebaseActiveOrgId(orgId)
  }
  return { orgId, organizations: [] }
}

export function FirebaseAuthProvider({ children }: { children: ReactNode }) {
  const [enabled, setEnabled] = useState(false)
  const [status, setStatus] = useState<FirebaseAuthContextValue['status']>('loading')
  const [user, setUser] = useState<User | null>(null)
  const [activeOrgId, setActiveOrgId] = useState<string | null>(null)
  const [organizations, setOrganizations] = useState<FirebaseOrgSummary[]>([])

  const reloadOrganizations = useCallback(async () => {
    if (!enabled) {
      return
    }
    const payload = await fetchFirebaseMe()
    setOrganizations(payload.organizations)
    if (!isLocalWorkspaceScope($workspaceScope.get())) {
      setActiveOrgId(payload.user.activeOrgId)
      setFirebaseActiveOrgId(payload.user.activeOrgId)
    }
  }, [enabled])

  const switchToLocalProjects = useCallback(() => {
    switchToLocalWorkspace()
    setActiveOrgId(null)
  }, [])

  const refreshSession = useCallback(async () => {
    if (!enabled) {
      return
    }
    const current = getFirebaseAuth().currentUser
    if (!current) {
      return
    }
    const token = await getFirebaseIdToken(true)
    if (token) {
      setFirebaseIdToken(token)
    }
  }, [enabled])

  const switchOrganization = useCallback(async (orgId: string) => {
    switchToOrgWorkspace(orgId)
    const result = await setFirebaseActiveOrg(orgId)
    setOrganizations(result.organizations)
    setActiveOrgId(result.activeOrgId)
    setFirebaseActiveOrgId(result.activeOrgId)
    const current = getFirebaseAuth().currentUser
    if (current) {
      writeCachedFirebaseSession({
        uid: current.uid,
        email: current.email || '',
        activeOrgId: result.activeOrgId
      })
    }
    await applyOrgPreferences()
  }, [])

  const createTeam = useCallback(
    async (name: string) => {
      const org = await createFirebaseTeamOrg(name)
      await switchOrganization(org.id)
      await reloadOrganizations()
      return org
    },
    [reloadOrganizations, switchOrganization]
  )

  const inviteMember = useCallback(
    async (email: string, role: 'admin' | 'member' = 'member') => {
      if (!activeOrgId) {
        throw new Error('No active workspace')
      }
      await inviteOrgMember(activeOrgId, email, role)
    },
    [activeOrgId]
  )

  const removeMember = useCallback(
    async (memberUid: string) => {
      if (!activeOrgId) {
        throw new Error('No active workspace')
      }
      await removeOrgMember(activeOrgId, memberUid)
    },
    [activeOrgId]
  )

  const signOut = useCallback(async () => {
    await firebaseLogout()
    clearCachedFirebaseSession()
    setFirebaseIdToken(null)
    setFirebaseActiveOrgId(null)
    setUser(null)
    setActiveOrgId(null)
    setOrganizations([])
    setStatus('signed-out')
  }, [])

  useEffect(() => {
    let cancelled = false
    let unsubscribe: (() => void) | undefined

    void (async () => {
      const ready = await initializeFirebaseClient()
      if (cancelled) {
        return
      }
      if (!ready) {
        setEnabled(false)
        setStatus('disabled')
        return
      }

      setEnabled(true)
      const auth = getFirebaseAuth()
      await auth.authStateReady()
      if (cancelled) {
        return
      }

      unsubscribe = onAuthStateChanged(auth, currentUser => {
        void (async () => {
          if (!currentUser) {
            clearCachedFirebaseSession()
            setFirebaseIdToken(null)
            setFirebaseActiveOrgId(null)
            setUser(null)
            setActiveOrgId(null)
            setOrganizations([])
            setStatus('signed-out')
            return
          }

          setStatus('loading')
          setUser(currentUser)

          try {
            const session = await hydrateServerSession(currentUser)
            setActiveOrgId(session.orgId)
            setOrganizations(session.organizations)
            setStatus('signed-in')
          } catch {
            const token = await currentUser.getIdToken()
            setFirebaseIdToken(token)
            try {
              const me = await fetchFirebaseMe()
              const resolved = resolveWorkspaceScope(me.user.activeOrgId, me.organizations)
              setActiveOrgId(resolved.orgId)
              setOrganizations(me.organizations)
              if (!isLocalWorkspaceScope(resolved.scope) && resolved.orgId && currentUser) {
                writeCachedFirebaseSession({
                  uid: currentUser.uid,
                  email: currentUser.email || '',
                  activeOrgId: resolved.orgId
                })
              }
            } catch {
              const cached = restoreCachedSession(currentUser)
              setActiveOrgId(cached.orgId)
              setOrganizations(cached.organizations)
            }
            setStatus('signed-in')
            void applyOrgPreferences().catch(() => undefined)
          }
        })()
      })
    })()

    return () => {
      cancelled = true
      unsubscribe?.()
    }
  }, [])

  useEffect(() => {
    if (!enabled || status !== 'signed-in') {
      return
    }
    const id = window.setInterval(() => {
      void refreshSession()
    }, TOKEN_REFRESH_MS)
    return () => window.clearInterval(id)
  }, [enabled, refreshSession, status])

  const activeOrg = useMemo(
    () => organizations.find(org => org.id === activeOrgId) ?? null,
    [activeOrgId, organizations]
  )

  const value = useMemo(
    () => ({
      enabled,
      status,
      user,
      activeOrgId,
      organizations,
      activeOrg,
      signOut,
      refreshSession,
      switchToLocalProjects,
      switchOrganization,
      createTeam,
      inviteMember,
      removeMember,
      reloadOrganizations
    }),
    [
      activeOrg,
      activeOrgId,
      createTeam,
      enabled,
      inviteMember,
      organizations,
      refreshSession,
      reloadOrganizations,
      removeMember,
      signOut,
      status,
      switchToLocalProjects,
      switchOrganization,
      user
    ]
  )

  return <FirebaseAuthReactContext.Provider value={value}>{children}</FirebaseAuthReactContext.Provider>
}
