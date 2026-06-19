/** Detect the LivingColor project dashboard route inside the Hermes dashboard plugin tab. */

const PLUGIN_TAB_PREFIX = '/livingcolor/projects/'

export function isHermesPluginProjectDashboardPath(pathname = window.location.pathname): boolean {
  if (!pathname.includes(PLUGIN_TAB_PREFIX)) {
    return false
  }

  if (pathname.includes('/settings') || pathname.includes('/integrations')) {
    return false
  }

  const tail = pathname.split(PLUGIN_TAB_PREFIX)[1] ?? ''
  const segments = tail.split('/').filter(Boolean)
  return segments.length === 1
}

export function parseHermesPluginProjectKey(pathname = window.location.pathname): string | null {
  if (!pathname.includes(PLUGIN_TAB_PREFIX)) {
    return null
  }

  const segment = pathname.split(PLUGIN_TAB_PREFIX)[1]?.split('/')[0]
  return segment ? decodeURIComponent(segment).trim().toUpperCase() : null
}
