import { Link, useLocation } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Check, ChevronDown, FolderOpen, Plus } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { useFirebaseAuth } from '@/hooks/use-firebase-auth'

import { dashboardOutlineButtonProps } from './dashboard-ui'
import { projectRoute } from './project-navigation'
import type { WorkspaceProject } from './project-workspace-context'
import { useProjectWorkspace } from '@/hooks/use-project-workspace'
import { useStore } from '@nanostores/react'
import { $workspaceScope, isLocalWorkspaceScope } from '@/store/workspace-scope'

function projectStorageLabel(
  project: WorkspaceProject,
  localWorkspace: boolean
): string | null {
  if (localWorkspace || project.storage === 'both') {
    return null
  }
  if (project.storage === 'local') {
    return 'Local'
  }
  if (project.storage === 'cloud') {
    return 'Cloud'
  }
  return null
}

function SidebarTooltipItem({
  label,
  children,
  collapsed
}: {
  label: string
  children: React.ReactNode
  collapsed: boolean
}) {
  if (!collapsed) {
    return <>{children}</>
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="right" sideOffset={8}>
        {label}
      </TooltipContent>
    </Tooltip>
  )
}

export function ProjectSwitcher({
  collapsed = false,
  onCreateProject
}: {
  collapsed?: boolean
  onCreateProject: () => void
}) {
  const { projects, loading, activeProjectKey, selectProject } = useProjectWorkspace()
  const { activeOrg } = useFirebaseAuth()
  const workspaceScope = useStore($workspaceScope)
  const localWorkspace = isLocalWorkspaceScope(workspaceScope)
  const location = useLocation()

  const activeProject = projects.find(project => project.jiraProjectKey === activeProjectKey) ?? null
  const triggerLabel = activeProject?.projectName ?? 'Select project'

  if (loading) {
    return (
      <div className={cn('py-3', collapsed ? 'flex justify-center px-2' : 'px-4')}>
        <Skeleton className={cn(collapsed ? 'size-9 rounded-md' : 'h-9 w-full rounded-md')} />
      </div>
    )
  }

  if (projects.length === 0) {
    return (
      <div className={cn('space-y-2 py-3', collapsed ? 'flex justify-center px-2' : 'px-4')}>
        {!collapsed ? <p className="text-xs text-muted-foreground">No projects yet</p> : null}
        <Button
          onClick={onCreateProject}
          size={collapsed ? 'icon' : 'sm'}
          title={collapsed ? 'Create project' : undefined}
          variant="outline"
          className={cn(collapsed ? 'size-9' : 'w-full justify-start gap-2')}
        >
          <Plus className="size-4" />
          {!collapsed ? 'Create project' : null}
        </Button>
      </div>
    )
  }

  return (
    <div className={cn('py-3', collapsed ? 'flex justify-center px-2' : 'px-4')}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            aria-label="Select project"
            className={cn(
              collapsed ? 'size-9' : 'h-9 w-full justify-between gap-2 px-2.5 font-normal'
            )}
            size={collapsed ? 'icon' : 'default'}
            title={collapsed ? triggerLabel : undefined}
            variant="outline"
          >
            <FolderOpen className="size-4 shrink-0" />
            {!collapsed ? (
              <>
                <span className="min-w-0 flex-1 truncate text-left text-sm font-semibold">{triggerLabel}</span>
                <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
              </>
            ) : null}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="min-w-56 w-[var(--radix-dropdown-menu-trigger-width)]">
          <DropdownMenuLabel className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {localWorkspace ? 'Personal projects' : activeOrg ? `${activeOrg.name} · Projects` : 'Projects'}
          </DropdownMenuLabel>
          {projects.map(project => {
            const isActive =
              project.jiraProjectKey === activeProjectKey ||
              location.pathname.startsWith(projectRoute(project.jiraProjectKey))
            const storageLabel = projectStorageLabel(project, localWorkspace)
            return (
              <DropdownMenuItem
                className="flex items-center gap-2"
                key={project.jiraProjectKey}
                onClick={() => void selectProject(project.jiraProjectKey)}
              >
                <FolderOpen className="size-4 shrink-0" />
                <span className="min-w-0 flex-1 truncate">{project.projectName}</span>
                <span className="text-xs text-muted-foreground">{project.jiraProjectKey}</span>
                {storageLabel ? (
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                    {storageLabel}
                  </span>
                ) : null}
                {isActive ? <Check className="size-4 shrink-0 text-foreground" /> : null}
              </DropdownMenuItem>
            )
          })}
          <DropdownMenuSeparator />
          <DropdownMenuItem className="text-foreground focus:text-foreground" onClick={onCreateProject}>
            <Plus className="mr-2 size-4" />
            Create project
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

export function ProjectSwitcherTooltipProvider({ children }: { children: React.ReactNode }) {
  return <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
}

export { SidebarTooltipItem }
