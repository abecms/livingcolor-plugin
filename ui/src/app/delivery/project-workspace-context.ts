import { createContext } from 'react'

export type WorkspaceProjectStorage = 'local' | 'cloud' | 'both'

export interface WorkspaceProject {
  jiraProjectKey: string
  projectName: string
  updatedAt?: string
  storage?: WorkspaceProjectStorage
}

export interface ProjectWorkspaceContextValue {
  loading: boolean
  projects: WorkspaceProject[]
  activeProjectKey: string | null
  activeProject: WorkspaceProject | null
  refreshProjects: () => Promise<void>
  selectProject: (projectKey: string) => Promise<void>
  createProject: (jiraProjectKey: string, projectName: string) => Promise<WorkspaceProject>
  deleteProject: (projectKey: string) => Promise<void>
}

export const ProjectWorkspaceReactContext = createContext<ProjectWorkspaceContextValue | null>(null)
