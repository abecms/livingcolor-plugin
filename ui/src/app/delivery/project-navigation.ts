import type { IconComponent } from '@/lib/icons'
import { BarChart3, Globe, Settings } from '@/lib/icons'

import { DASHBOARD_ROUTE, DELIVERY_ROUTE, PROJECTS_ROUTE_PREFIX } from '../routes'

export interface ProjectTabDef {
  href: string
  label: string
  icon: IconComponent
}

export const PROJECT_TAB_DEFS: ProjectTabDef[] = [
  { href: '', label: 'Dashboard', icon: BarChart3 },
  { href: '/settings', label: 'Settings', icon: Settings },
  { href: '/integrations', label: 'Integrations', icon: Globe }
]

export function projectRoute(projectKey: string): string {
  return `${PROJECTS_ROUTE_PREFIX}/${encodeURIComponent(projectKey.trim().toUpperCase())}`
}

export function projectTabRoute(projectKey: string, tabHref: string): string {
  const base = projectRoute(projectKey)
  return tabHref ? `${base}${tabHref}` : base
}

/** Project chat lives in the dashboard side panel — no dedicated route. */
export function projectChatRoute(projectKey: string, _sessionId?: string): string {
  return projectRoute(projectKey)
}

export function isProjectDashboardPath(pathname: string): boolean {
  if (!pathname.startsWith(`${PROJECTS_ROUTE_PREFIX}/`)) {
    return false
  }
  const subpath = getProjectSubpath(pathname)
  return subpath === '' || subpath === '/'
}

export function parseProjectKeyFromPath(pathname: string): string | null {
  if (!pathname.startsWith(`${PROJECTS_ROUTE_PREFIX}/`)) {
    return null
  }
  const remainder = pathname.slice(PROJECTS_ROUTE_PREFIX.length + 1)
  const segment = remainder.split('/')[0]
  return segment ? decodeURIComponent(segment).toUpperCase() : null
}

export function getProjectSubpath(pathname: string): string {
  if (!pathname.startsWith(`${PROJECTS_ROUTE_PREFIX}/`)) {
    return ''
  }
  const remainder = pathname.slice(PROJECTS_ROUTE_PREFIX.length + 1)
  const slashIndex = remainder.indexOf('/')
  return slashIndex >= 0 ? remainder.slice(slashIndex) : ''
}

type ProjectKeyRef = { id: string; slug?: string }

/** After an org switch, redirect away from a project route that no longer exists in the active org. */
export function getProjectRedirectOnOrgChange(
  pathname: string,
  projects: ProjectKeyRef[]
): string | null {
  const projectKey = parseProjectKeyFromPath(pathname)
  if (!projectKey) {
    return null
  }

  const belongsToOrg = projects.some(project => project.id === projectKey || project.slug === projectKey)
  if (belongsToOrg) {
    return null
  }

  const subpath = getProjectSubpath(pathname)
  if (projects.length > 0) {
    const first = projects[0]
    return projectRoute(first.slug || first.id) + subpath
  }

  return '/'
}

export function isProjectWorkspacePath(pathname: string): boolean {
  return (
    pathname === '/' ||
    pathname === DASHBOARD_ROUTE ||
    pathname === DELIVERY_ROUTE ||
    pathname.startsWith(`${PROJECTS_ROUTE_PREFIX}/`)
  )
}

export function isProjectTabActive(pathname: string, projectKey: string, tabHref: string): boolean {
  const base = projectRoute(projectKey)
  if (tabHref === '') {
    return pathname === base || pathname === `${base}/`
  }
  return pathname === `${base}${tabHref}` || pathname.startsWith(`${base}${tabHref}/`)
}

