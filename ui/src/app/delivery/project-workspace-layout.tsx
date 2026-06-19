import { useState } from 'react'
import { Link, Navigate, Outlet, useParams } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ChevronLeft, ChevronRight, Plus } from '@/lib/icons'
import { LivingColorSidebarBrand } from '@/components/livingcolor-logo'
import { cn } from '@/lib/utils'
import { useFirebaseAuth } from '@/hooks/use-firebase-auth'

import { DASHBOARD_ROUTE } from '../routes'

import { CreateProjectDialog } from './create-project-dialog'
import { dashboardPrimaryButtonProps } from './dashboard-ui'
import { ProjectSidebarNav } from './project-sidebar-nav'
import { ProjectSwitcher, ProjectSwitcherTooltipProvider, SidebarTooltipItem } from './project-switcher'
import { useProjectWorkspace } from '@/hooks/use-project-workspace'

import { ProjectWorkspaceProvider } from './project-workspace-provider'
import { ProjectWorkspaceSplit } from './project-workspace-split'
import { useProjectSidebarCollapsed } from './sidebar-preference'
import { WorkspaceOrgSwitcher } from './workspace-org-switcher'
import { WorkspaceSidebarUserMenu } from './workspace-sidebar-user-menu'
import { projectRoute, projectTabRoute } from './project-navigation'

const SIDEBAR_WIDTH_EXPANDED = 'w-60'
const SIDEBAR_WIDTH_COLLAPSED = 'w-14'

function ProjectWorkspaceEmptyState({ onCreateProject }: { onCreateProject: () => void }) {
  const { enabled, status } = useFirebaseAuth()

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
      <p className="max-w-md text-sm text-muted-foreground">
        Create your first project to get started. Use the sidebar switcher or the button below.
      </p>
      {enabled && status === 'loading' ? (
        <p className="text-xs text-muted-foreground">Syncing workspace…</p>
      ) : (
        <Button onClick={onCreateProject} type="button" {...dashboardPrimaryButtonProps()}>
          <Plus className="mr-2 size-4" />
          Create project
        </Button>
      )}
    </div>
  )
}

function ProjectWorkspaceMain({
  targetTab = ''
}: {
  targetTab?: '' | '/settings' | '/integrations'
}) {
  const params = useParams()
  const projectKey = params.projectKey?.trim().toUpperCase()
  const { projects, loading, activeProjectKey } = useProjectWorkspace()
  const [createOpen, setCreateOpen] = useState(false)

  if (projectKey) {
    return <Outlet />
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading projects…</p>
      </div>
    )
  }

  const targetKey = activeProjectKey ?? projects[0]?.jiraProjectKey
  if (targetKey) {
    return <Navigate replace to={projectTabRoute(targetKey, targetTab)} />
  }

  return (
    <>
      <ProjectWorkspaceEmptyState onCreateProject={() => setCreateOpen(true)} />
      <CreateProjectDialog onOpenChange={setCreateOpen} open={createOpen} />
    </>
  )
}

function ProjectWorkspaceSidebar() {
  const [collapsed, toggleCollapsed] = useProjectSidebarCollapsed()
  const [createOpen, setCreateOpen] = useState(false)
  const { enabled } = useFirebaseAuth()

  const content = (
    <>
      <div
        className={cn(
          'relative flex flex-col justify-center gap-2 border-b border-border',
          collapsed ? 'items-center px-2 py-3' : 'px-4 py-3'
        )}
      >
        <div className={cn('flex items-center', collapsed ? 'mx-auto justify-center' : 'w-full')}>
          <SidebarTooltipItem collapsed={collapsed} label="LivingColor">
            <Link
              className={cn('flex items-center', collapsed ? 'size-9 justify-center' : 'min-h-7')}
              to={DASHBOARD_ROUTE}
            >
              <LivingColorSidebarBrand collapsed={collapsed} />
            </Link>
          </SidebarTooltipItem>
        </div>
        {enabled ? (
          <WorkspaceOrgSwitcher
            className={collapsed ? 'size-8 justify-center p-0' : '-ml-1 h-7 justify-start px-1'}
            iconOnly={collapsed}
          />
        ) : (
          <p className={cn('text-xs text-muted-foreground', collapsed ? 'sr-only' : 'px-1')}>
            Personal projects
          </p>
        )}
        <button
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className={cn(
            'absolute -right-[14px] bottom-2 z-10 flex size-6 items-center justify-center',
            'rounded-full border border-border bg-card text-muted-foreground shadow-sm',
            'transition-colors hover:bg-accent hover:text-foreground',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
          )}
          onClick={toggleCollapsed}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          type="button"
        >
          {collapsed ? <ChevronRight className="size-3.5" /> : <ChevronLeft className="size-3.5" />}
        </button>
      </div>

      <ProjectSwitcher collapsed={collapsed} onCreateProject={() => setCreateOpen(true)} />

      <ScrollArea className={cn('min-h-0 flex-1', collapsed ? 'px-1.5' : 'px-0')}>
        <ProjectSidebarNav collapsed={collapsed} />
      </ScrollArea>

      <WorkspaceSidebarUserMenu collapsed={collapsed} />
      <CreateProjectDialog onOpenChange={setCreateOpen} open={createOpen} />
    </>
  )

  return (
    <aside
      className={cn(
        'flex h-full flex-col border-r border-border bg-card transition-[width] duration-300 ease-in-out',
        collapsed ? SIDEBAR_WIDTH_COLLAPSED : SIDEBAR_WIDTH_EXPANDED
      )}
    >
      {collapsed ? <ProjectSwitcherTooltipProvider>{content}</ProjectSwitcherTooltipProvider> : content}
    </aside>
  )
}

function ProjectWorkspaceShell({
  targetTab = ''
}: {
  targetTab?: '' | '/settings' | '/integrations'
}) {
  return (
    <div className="flex h-full min-w-0 overflow-hidden">
      <ProjectWorkspaceSidebar />
      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <ProjectWorkspaceSplit>
          <ProjectWorkspaceMain targetTab={targetTab} />
        </ProjectWorkspaceSplit>
      </div>
    </div>
  )
}

export function ProjectWorkspaceLayout() {
  return (
    <ProjectWorkspaceProvider>
      <ProjectWorkspaceShell />
    </ProjectWorkspaceProvider>
  )
}

export function ProjectWorkspaceLandingRedirect({
  targetTab = ''
}: {
  targetTab?: '' | '/settings' | '/integrations'
} = {}) {
  return (
    <ProjectWorkspaceProvider>
      <ProjectWorkspaceShell targetTab={targetTab} />
    </ProjectWorkspaceProvider>
  )
}
