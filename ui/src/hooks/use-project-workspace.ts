import { useContext } from 'react'

import {
  ProjectWorkspaceReactContext,
  type ProjectWorkspaceContextValue
} from '@/app/delivery/project-workspace-context'

export function useProjectWorkspace(): ProjectWorkspaceContextValue {
  const ctx = useContext(ProjectWorkspaceReactContext)
  if (!ctx) {
    throw new Error('useProjectWorkspace must be used within ProjectWorkspaceProvider')
  }
  return ctx
}
