/**
 * Slim Hermes API surface for the LivingColor plugin dashboard tab.
 * Delivery UI only needs Jira/GitLab MCP helpers and config reads.
 */
import { callDesktopApi } from '@/lib/desktop-api'
import type { GitHubConnectResponse, GitHubConnectionStatus } from '@/lib/github-dashboard'
import type { GitLabConnectResponse, GitLabConnectionStatus } from '@/lib/gitlab-dashboard'
import type { JiraConnectResponse, JiraDashboardPayload } from '@/lib/jira-dashboard'
import type { LivingColorConfigRecord } from '@/types/livingcolor'

const JIRA_DASHBOARD_TIMEOUT_MS = 30_000
const JIRA_CONNECT_TIMEOUT_MS = 330_000

export function fetchJiraDashboard(
  options: { projectKey?: string | null; reconnect?: boolean } = {}
): Promise<JiraDashboardPayload> {
  const params = new URLSearchParams()

  if (options.reconnect) {
    params.set('reconnect', '1')
  }

  if (options.projectKey) {
    params.set('project', options.projectKey)
  }

  const query = params.toString() ? `?${params.toString()}` : ''
  const reconnect = options.reconnect ?? false

  return callDesktopApi<JiraDashboardPayload>({
    path: `/api/jira/dashboard${query}`,
    timeoutMs: reconnect ? JIRA_CONNECT_TIMEOUT_MS : JIRA_DASHBOARD_TIMEOUT_MS
  })
}

export function connectJiraMcp(): Promise<JiraConnectResponse> {
  return callDesktopApi<JiraConnectResponse>({
    path: '/api/jira/connect',
    method: 'POST',
    timeoutMs: JIRA_CONNECT_TIMEOUT_MS
  })
}

export function connectGitlabMcp(serverName = 'gitlab'): Promise<GitLabConnectResponse> {
  return callDesktopApi<GitLabConnectResponse>({
    path: `/api/mcp/servers/${encodeURIComponent(serverName)}/connect`,
    method: 'POST',
    timeoutMs: JIRA_CONNECT_TIMEOUT_MS
  })
}

export function fetchGitlabStatus(serverName = 'gitlab'): Promise<GitLabConnectionStatus> {
  return callDesktopApi<GitLabConnectionStatus>({
    path: `/api/mcp/servers/${encodeURIComponent(serverName)}/status`,
    timeoutMs: JIRA_DASHBOARD_TIMEOUT_MS
  })
}

export function connectGithubMcp(serverName = 'github'): Promise<GitHubConnectResponse> {
  return callDesktopApi<GitHubConnectResponse>({
    path: `/api/mcp/servers/${encodeURIComponent(serverName)}/connect`,
    method: 'POST',
    timeoutMs: JIRA_CONNECT_TIMEOUT_MS
  })
}

export function fetchGithubStatus(serverName = 'github'): Promise<GitHubConnectionStatus> {
  return callDesktopApi<GitHubConnectionStatus>({
    path: `/api/mcp/servers/${encodeURIComponent(serverName)}/status`,
    timeoutMs: JIRA_DASHBOARD_TIMEOUT_MS
  })
}

export function fetchIntegrationsMcpStatus(): Promise<{
  jira: import('@/lib/jira-dashboard').JiraConnectionStatus & { configured?: boolean; serverName?: string | null }
  gitlab: GitLabConnectionStatus & { configured?: boolean; serverName?: string | null }
  github: GitHubConnectionStatus & { configured?: boolean; serverName?: string | null }
}> {
  return callDesktopApi({
    path: '/api/mcp/integrations/status',
    timeoutMs: JIRA_DASHBOARD_TIMEOUT_MS
  })
}

export function getLivingColorConfigRecord(): Promise<LivingColorConfigRecord> {
  return callDesktopApi<LivingColorConfigRecord>({ path: '/api/config' })
}

export function saveLivingColorConfig(config: LivingColorConfigRecord): Promise<{ ok: boolean }> {
  return callDesktopApi<{ ok: boolean }>({
    path: '/api/config',
    method: 'PUT',
    body: { config }
  })
}

export function saveMcpServerConfig(
  name: string,
  serverConfig: Record<string, unknown>
): Promise<{ ok: boolean; name: string }> {
  return callDesktopApi<{ ok: boolean; name: string }>({
    path: `/api/mcp/servers/${encodeURIComponent(name)}`,
    method: 'PUT',
    body: serverConfig,
    timeoutMs: 30_000
  })
}

export function testMcpServer(name: string): Promise<{ ok: boolean; error?: string; tools?: Array<{ name: string; description?: string }> }> {
  return callDesktopApi({
    path: `/api/mcp/servers/${encodeURIComponent(name)}/test`,
    method: 'POST',
    timeoutMs: JIRA_CONNECT_TIMEOUT_MS
  })
}

export function fetchJiraMcpStatus(serverName = 'jira'): Promise<import('@/lib/jira-dashboard').JiraConnectionStatus> {
  return callDesktopApi({
    path: `/api/mcp/servers/${encodeURIComponent(serverName)}/status`,
    timeoutMs: JIRA_DASHBOARD_TIMEOUT_MS
  })
}

export type { LivingColorConfigRecord } from '@/types/livingcolor'
