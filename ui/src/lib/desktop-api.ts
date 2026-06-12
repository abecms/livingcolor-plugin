/**
 * Replacement for agent-lc's callDesktopApi (Electron IPC + Firebase).
 * Routes everything through the Hermes dashboard SDK fetchJSON, which
 * handles auth in both loopback and gated modes. Path prefixes are
 * rewritten: /api/delivery/* and /api/jira/* → /api/plugins/livingcolor/*.
 */
export interface LivingColorApiRequest {
  path: string
  method?: string
  body?: unknown
  timeoutMs?: number
}

function rewrite(path: string): string {
  return path
    .replace(/^\/api\/delivery\//, '/api/plugins/livingcolor/delivery/')
    .replace(/^\/api\/jira\//, '/api/plugins/livingcolor/jira/')
}

export async function callDesktopApi<T>(request: LivingColorApiRequest): Promise<T> {
  const sdk = (window as any).__HERMES_PLUGIN_SDK__
  if (!sdk) throw new Error('Hermes plugin SDK unavailable')
  const init: RequestInit = { method: request.method ?? 'GET' }
  if (request.body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify(request.body)
  }
  return sdk.fetchJSON(rewrite(request.path), init) as Promise<T>
}
