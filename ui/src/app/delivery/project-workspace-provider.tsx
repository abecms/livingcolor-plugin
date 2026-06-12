import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import { useFirebaseAuth } from '@/hooks/use-firebase-auth'
import { createLocalProject, fetchLocalProjects } from '@/lib/delivery'
import {
  createOrgProject,
  deleteOrgProject,
  fetchOrgProjects,
  saveFirebasePreferences,
  type FirebaseOrgProject
} from '@/lib/firebase-session'
import { writeStoredJiraProjectKey } from '@/lib/jira-project-storage'
import { bumpProjectConfigRevision } from '@/store/project-config'
import { LOCAL_ORG_ID, setProjectApiContext } from '@/store/project-api-context'
import { $workspaceScope, isLocalWorkspaceScope, switchToLocalWorkspace } from '@/store/workspace-scope'

import { getProjectRedirectOnOrgChange, projectRoute } from './project-navigation'
import {
  ProjectWorkspaceReactContext,
  type WorkspaceProject,
  type WorkspaceProjectStorage
} from './project-workspace-context'

function normalizeProject(
  row: FirebaseOrgProject,
  storage?: WorkspaceProjectStorage
): WorkspaceProject {
  return {
    jiraProjectKey: row.jiraProjectKey.trim().toUpperCase(),
    projectName: row.projectName?.trim() || row.jiraProjectKey,
    updatedAt: row.updatedAt,
    storage
  }
}

function mergeWorkspaceProjects(
  local: WorkspaceProject[],
  cloud: WorkspaceProject[]
): WorkspaceProject[] {
  const merged = new Map<string, WorkspaceProject>()
  for (const project of local) {
    merged.set(project.jiraProjectKey, { ...project, storage: 'local' })
  }
  for (const project of cloud) {
    const existing = merged.get(project.jiraProjectKey)
    merged.set(project.jiraProjectKey, {
      ...project,
      projectName: project.projectName || existing?.projectName || project.jiraProjectKey,
      updatedAt: project.updatedAt ?? existing?.updatedAt,
      storage: existing ? 'both' : 'cloud'
    })
  }
  return [...merged.values()].sort((left, right) =>
    left.jiraProjectKey.localeCompare(right.jiraProjectKey)
  )
}

export function ProjectWorkspaceProvider({ children }: { children: ReactNode }) {
  const { enabled, activeOrgId, status } = useFirebaseAuth()
  const workspaceScope = useStore($workspaceScope)
  const params = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [loading, setLoading] = useState(true)
  const [projects, setProjects] = useState<WorkspaceProject[]>([])

  const routeProjectKey = params.projectKey?.trim().toUpperCase() || null

  const refreshProjects = useCallback(async () => {
    setLoading(true)
    try {
      const localPayload = await fetchLocalProjects()
      const localProjects = localPayload.projects.map(row => normalizeProject(row, 'local'))

      if (!enabled || isLocalWorkspaceScope(workspaceScope)) {
        setProjects(localProjects)
        return
      }
      if (activeOrgId && status === 'signed-in') {
        try {
          const cloudPayload = await fetchOrgProjects(activeOrgId)
          const cloudProjects = cloudPayload.projects.map(row => normalizeProject(row, 'cloud'))
          setProjects(mergeWorkspaceProjects(localProjects, cloudProjects))
          return
        } catch {
          setProjects(localProjects)
          return
        }
      }
      setProjects(localProjects)
    } catch {
      setProjects([])
    } finally {
      setLoading(false)
    }
  }, [activeOrgId, enabled, status, workspaceScope])

  useEffect(() => {
    void refreshProjects()
  }, [refreshProjects])

  useEffect(() => {
    if (loading) {
      return
    }
    const redirect = getProjectRedirectOnOrgChange(
      location.pathname,
      projects.map(project => ({ id: project.jiraProjectKey }))
    )
    if (redirect) {
      navigate(redirect, { replace: true })
    }
  }, [activeOrgId, loading, location.pathname, navigate, projects, workspaceScope])

  const activeProjectKey = useMemo(() => {
    if (routeProjectKey) {
      return routeProjectKey
    }
    return projects[0]?.jiraProjectKey ?? null
  }, [projects, routeProjectKey])

  const activeProject = useMemo(
    () => projects.find(project => project.jiraProjectKey === activeProjectKey) ?? null,
    [activeProjectKey, projects]
  )

  useEffect(() => {
    const orgId = isLocalWorkspaceScope(workspaceScope) ? LOCAL_ORG_ID : activeOrgId
    setProjectApiContext(orgId, activeProjectKey)
  }, [activeOrgId, activeProjectKey, workspaceScope])

  const persistSelection = useCallback(
    async (projectKey: string) => {
      writeStoredJiraProjectKey(projectKey)
      bumpProjectConfigRevision()
      if (enabled && !isLocalWorkspaceScope(workspaceScope) && activeOrgId && status === 'signed-in') {
        try {
          await saveFirebasePreferences(projectKey)
        } catch {
          // Best-effort when backend is offline.
        }
      }
    },
    [activeOrgId, enabled, status, workspaceScope]
  )

  const selectProject = useCallback(
    async (projectKey: string) => {
      const normalized = projectKey.trim().toUpperCase()
      const target = projects.find(project => project.jiraProjectKey === normalized)
      if (enabled && target?.storage === 'local' && !isLocalWorkspaceScope(workspaceScope)) {
        switchToLocalWorkspace()
      }
      await persistSelection(normalized)
      navigate(projectRoute(normalized))
    },
    [enabled, navigate, persistSelection, projects, workspaceScope]
  )

  const createProject = useCallback(
    async (jiraProjectKey: string, projectName: string) => {
      const key = jiraProjectKey.trim().toUpperCase()
      const name = projectName.trim()
      if (!enabled || isLocalWorkspaceScope(workspaceScope)) {
        const created = normalizeProject(await createLocalProject(key, name))
        await refreshProjects()
        await selectProject(created.jiraProjectKey)
        return created
      }
      if (status === 'signed-in') {
        if (!activeOrgId) {
          throw new Error('Workspace is still loading. Wait a moment and try again.')
        }
        const result = await createOrgProject(activeOrgId, key, name)
        const created = normalizeProject(result.project)
        await refreshProjects()
        await selectProject(created.jiraProjectKey)
        return created
      }
      throw new Error('Sign in or switch to personal local projects to create a project.')
    },
    [activeOrgId, enabled, refreshProjects, selectProject, status, workspaceScope]
  )

  const deleteProject = useCallback(
    async (projectKey: string) => {
      const normalized = projectKey.trim().toUpperCase()
      if (enabled && !isLocalWorkspaceScope(workspaceScope) && activeOrgId && status === 'signed-in') {
        await deleteOrgProject(activeOrgId, normalized)
      }
      const remaining = projects.filter(project => project.jiraProjectKey !== normalized)
      setProjects(remaining)
      const next = remaining[0]?.jiraProjectKey
      if (next) {
        await selectProject(next)
      } else {
        navigate('/')
      }
      await refreshProjects()
    },
    [activeOrgId, enabled, navigate, projects, refreshProjects, selectProject, status, workspaceScope]
  )

  const value = useMemo(
    () => ({
      loading,
      projects,
      activeProjectKey,
      activeProject,
      refreshProjects,
      selectProject,
      createProject,
      deleteProject
    }),
    [
      activeProject,
      activeProjectKey,
      createProject,
      deleteProject,
      loading,
      projects,
      refreshProjects,
      selectProject
    ]
  )

  return (
    <ProjectWorkspaceReactContext.Provider value={value}>{children}</ProjectWorkspaceReactContext.Provider>
  )
}
