/** Build absolute in-app paths for the Hermes host shell (outside the plugin basename). */

export const HERMES_MCP_SETTINGS_PATH = '/mcp'

export function hermesBasePath(): string {
  const raw = (window as Window & { __HERMES_BASE_PATH__?: string }).__HERMES_BASE_PATH__
  if (typeof raw !== 'string') {
    return ''
  }
  return raw.replace(/\/$/, '')
}

export function buildHermesAppPath(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`
  const base = hermesBasePath()
  const relative = base ? `${base}${normalized}` : normalized
  if (typeof window !== 'undefined' && window.location?.origin) {
    return `${window.location.origin}${relative}`
  }
  return relative
}
