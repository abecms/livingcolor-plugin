import { atom } from 'nanostores'

import { setFirebaseActiveOrgId } from '@/store/firebase-auth'

const WORKSPACE_SCOPE_STORAGE_KEY = 'livingcolor.workspace.scope'

export type WorkspaceScope =
  | { mode: 'local' }
  | { mode: 'org'; orgId: string }

export const $workspaceScope = atom<WorkspaceScope>({ mode: 'local' })

function writeStoredWorkspaceScope(scope: WorkspaceScope): void {
  if (typeof window === 'undefined') {
    return
  }
  try {
    const value = scope.mode === 'local' ? 'local' : `org:${scope.orgId}`
    window.localStorage.setItem(WORKSPACE_SCOPE_STORAGE_KEY, value)
  } catch {
    // ignore quota / privacy mode
  }
}

export function readStoredWorkspaceScope(): WorkspaceScope | null {
  if (typeof window === 'undefined') {
    return null
  }
  try {
    const raw = window.localStorage.getItem(WORKSPACE_SCOPE_STORAGE_KEY)?.trim()
    if (!raw) {
      return null
    }
    if (raw === 'local') {
      return { mode: 'local' }
    }
    if (raw.startsWith('org:')) {
      const orgId = raw.slice(4).trim()
      return orgId ? { mode: 'org', orgId } : null
    }
    return { mode: 'org', orgId: raw }
  } catch {
    return null
  }
}

export function isLocalWorkspaceScope(scope: WorkspaceScope): boolean {
  return scope.mode === 'local'
}

export function applyWorkspaceScope(scope: WorkspaceScope): void {
  $workspaceScope.set(scope)
  writeStoredWorkspaceScope(scope)
  if (scope.mode === 'local') {
    setFirebaseActiveOrgId(null)
    return
  }
  setFirebaseActiveOrgId(scope.orgId)
}

export function switchToLocalWorkspace(): void {
  applyWorkspaceScope({ mode: 'local' })
}

export function switchToOrgWorkspace(orgId: string): void {
  const cleaned = orgId.trim()
  if (!cleaned) {
    return
  }
  applyWorkspaceScope({ mode: 'org', orgId: cleaned })
}

export function hydrateWorkspaceScopeFromStorage(): WorkspaceScope | null {
  const stored = readStoredWorkspaceScope()
  if (!stored) {
    return null
  }
  applyWorkspaceScope(stored)
  return stored
}
