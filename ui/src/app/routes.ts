export const DELIVERY_ROUTE = '/delivery'
export const PROJECTS_ROUTE_PREFIX = '/projects'
export const SESSION_ROUTE_PREFIX = '/'
export const NEW_CHAT_ROUTE = '/'
export const SETTINGS_ROUTE = '/settings'
export const COMMAND_CENTER_ROUTE = '/command-center'
export const DASHBOARD_ROUTE = '/dashboard'
export const VISUALQ_ROUTE = '/visualq'
export const SKILLS_ROUTE = '/skills'
export const MESSAGING_ROUTE = '/messaging'
export const ARTIFACTS_ROUTE = '/artifacts'
export const CRON_ROUTE = '/cron'
export const PROFILES_ROUTE = '/profiles'
export const AGENTS_ROUTE = '/agents'
export const FIREBASE_GOOGLE_OAUTH_ROUTE = '/auth/firebase-google'

export type AppView =
  | 'agents'
  | 'artifacts'
  | 'chat'
  | 'command-center'
  | 'cron'
  | 'dashboard'
  | 'delivery'
  | 'visualq'
  | 'messaging'
  | 'profiles'
  | 'settings'
  | 'skills'

export type AppRouteId =
  | 'agents'
  | 'artifacts'
  | 'command-center'
  | 'cron'
  | 'dashboard'
  | 'delivery'
  | 'visualq'
  | 'messaging'
  | 'new'
  | 'profiles'
  | 'settings'
  | 'skills'

export interface AppRoute {
  id: AppRouteId
  path: string
  view: AppView
}

export const APP_ROUTES = [
  { id: 'delivery', path: DELIVERY_ROUTE, view: 'delivery' },
  { id: 'dashboard', path: DASHBOARD_ROUTE, view: 'dashboard' },
  { id: 'visualq', path: VISUALQ_ROUTE, view: 'visualq' },
  { id: 'settings', path: SETTINGS_ROUTE, view: 'settings' },
  { id: 'command-center', path: COMMAND_CENTER_ROUTE, view: 'command-center' },
  { id: 'skills', path: SKILLS_ROUTE, view: 'skills' },
  { id: 'messaging', path: MESSAGING_ROUTE, view: 'messaging' },
  { id: 'artifacts', path: ARTIFACTS_ROUTE, view: 'artifacts' },
  { id: 'cron', path: CRON_ROUTE, view: 'cron' },
  { id: 'profiles', path: PROFILES_ROUTE, view: 'profiles' },
  { id: 'agents', path: AGENTS_ROUTE, view: 'agents' }
] as const satisfies readonly AppRoute[]

const APP_VIEW_BY_PATH = new Map<string, AppView>(APP_ROUTES.map(route => [route.path, route.view]))
const RESERVED_PATHS: ReadonlySet<string> = new Set(APP_ROUTES.map(route => route.path))

// Views that render as a full-screen modal card (OverlayView) over the shell.
// While one is open the app's titlebar control clusters must hide so they don't
// bleed over the overlay (they sit at a higher z-index than the overlay card).
export const OVERLAY_VIEWS: ReadonlySet<AppView> = new Set(['agents', 'command-center', 'cron', 'profiles', 'settings'])

export function isOverlayView(view: AppView): boolean {
  return OVERLAY_VIEWS.has(view)
}

export function isNewChatRoute(pathname: string): boolean {
  return false
}

export function isProjectChatPath(pathname: string): boolean {
  return pathname.startsWith(`${PROJECTS_ROUTE_PREFIX}/`) && pathname.includes('/chat')
}

export function projectChatSessionId(pathname: string): string | null {
  if (!isProjectChatPath(pathname)) {
    return null
  }
  const parts = pathname.split('/').filter(Boolean)
  const chatIndex = parts.indexOf('chat')
  if (chatIndex < 0) {
    return null
  }
  const sessionPart = parts[chatIndex + 1]
  return sessionPart ? decodeURIComponent(sessionPart) : null
}

export function routeSessionId(pathname: string): string | null {
  const projectSession = projectChatSessionId(pathname)
  if (projectSession) {
    return projectSession
  }

  if (!pathname.startsWith(SESSION_ROUTE_PREFIX) || RESERVED_PATHS.has(pathname)) {
    return null
  }

  const id = pathname.slice(SESSION_ROUTE_PREFIX.length)

  return id && !id.includes('/') ? decodeURIComponent(id) : null
}

export function sessionRoute(sessionId: string): string {
  return `${SESSION_ROUTE_PREFIX}${encodeURIComponent(sessionId)}`
}

export function appViewForPath(pathname: string): AppView {
  if (pathname === NEW_CHAT_ROUTE) {
    return 'dashboard'
  }

  if (pathname.startsWith(`${PROJECTS_ROUTE_PREFIX}/`)) {
    if (pathname.includes('/settings') || pathname.includes('/integrations')) {
      return 'delivery'
    }
    return 'dashboard'
  }

  if (routeSessionId(pathname)) {
    return 'chat'
  }

  return APP_VIEW_BY_PATH.get(pathname) ?? 'chat'
}
