import { Link, useLocation } from 'react-router-dom'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

import {
  isProjectTabActive,
  parseProjectKeyFromPath,
  PROJECT_TAB_DEFS,
  projectTabRoute
} from './project-navigation'
import { useProjectWorkspace } from '@/hooks/use-project-workspace'

function NavItem({
  href,
  label,
  icon: Icon,
  active,
  collapsed,
  projectKey
}: {
  href: string
  label: string
  icon: (typeof PROJECT_TAB_DEFS)[number]['icon']
  active: boolean
  collapsed: boolean
  projectKey: string
}) {
  const link = (
    <Link
      className={cn(
        'flex items-center rounded-md text-sm transition-colors',
        collapsed ? 'size-9 justify-center' : 'gap-2 px-2 py-1.5',
        active
          ? 'bg-white/10 font-medium text-white'
          : 'text-white/55 hover:bg-white/5 hover:text-white/90'
      )}
      title={collapsed ? label : undefined}
      to={projectTabRoute(projectKey, href)}
    >
      <Icon className="size-4 shrink-0" />
      {!collapsed ? <span className="min-w-0 flex-1 truncate">{label}</span> : null}
    </Link>
  )

  if (!collapsed) {
    return link
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right" sideOffset={8}>
        {label}
      </TooltipContent>
    </Tooltip>
  )
}

function SectionHeading({ label, collapsed }: { label: string; collapsed?: boolean }) {
  if (collapsed) {
    return null
  }

  return (
    <div className="flex items-center justify-between px-2 pb-1 pt-3 first:pt-1">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-white/40">{label}</span>
    </div>
  )
}

export function ProjectSidebarNav({ collapsed = false }: { collapsed?: boolean }) {
  const { activeProjectKey } = useProjectWorkspace()
  const location = useLocation()
  const projectKey = parseProjectKeyFromPath(location.pathname) ?? activeProjectKey

  if (!projectKey) {
    return null
  }

  return (
    <nav className={cn('space-y-0.5', collapsed ? 'flex flex-col items-center' : 'px-2')}>
      <SectionHeading collapsed={collapsed} label="Project" />
      {PROJECT_TAB_DEFS.map(tab => (
        <NavItem
          active={isProjectTabActive(location.pathname, projectKey, tab.href)}
          collapsed={collapsed}
          href={tab.href}
          icon={tab.icon}
          key={tab.href || 'dashboard'}
          label={tab.label}
          projectKey={projectKey}
        />
      ))}
    </nav>
  )
}
