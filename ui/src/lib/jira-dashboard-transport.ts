import { connectJiraMcp, fetchJiraDashboard, fetchJiraMcpStatus, getLivingColorConfigRecord, saveMcpServerConfig } from '@/hermes'
import type { JiraConnectResponse, JiraDashboardPayload } from '@/lib/jira-dashboard'
import {
  buildJiraMcpAtlassianConfig,
  JIRA_ATLASSIAN_API_TOKEN_URL,
  JIRA_MCP_PRESET_NAME,
  readJiraSavedCredentials,
  type JiraEnvCredentials
} from '@/lib/jira-mcp'
import { readMcpServers, resolveJiraMcpServer } from '@/lib/mcp-server-resolver'

export type GatewayRequester = <T>(method: string, params?: Record<string, unknown>) => Promise<T>

const SAMPLE_DASHBOARD: JiraDashboardPayload = {
  actions: [
    'Review open priorities and identify blockers',
    'Turn the next product goal into clear Jira tickets',
    'Prepare a VisualQ update for stakeholders',
    'Summarize risks, owners, and next actions'
  ],
  blockers: [],
  connection: {
    authenticated: false,
    message: 'Connect Jira to replace sample data with live priorities and blockers.',
    status: 'disconnected',
    toolCount: 0
  },
  metrics: [
    {
      detail: 'Sample indicator — connect Jira for live delivery signals.',
      label: 'Delivery confidence',
      tone: 'good',
      value: '82%'
    },
    {
      detail: 'Two priorities need clarification before they move forward.',
      label: 'Sprint health',
      tone: 'warning',
      value: 'Watch'
    },
    {
      detail: 'Use Connect Jira or API token to link your Atlassian workspace.',
      label: 'Jira status',
      tone: 'neutral',
      value: 'Ready to connect'
    }
  ],
  priorities: [],
  projects: [],
  selectedProjectKey: null,
  risks: [
    {
      detail: 'Use the sample data for orientation until Jira is connected.',
      label: 'Jira not connected'
    },
    {
      detail: 'Make sure every priority has one accountable owner before it moves forward.',
      label: 'Unclear ownership'
    }
  ],
  sampleData: true
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function isUnavailableRoute(error: unknown): boolean {
  const message = errorMessage(error).toLowerCase()

  return (
    message.includes('404') ||
    message.includes('405') ||
    message.includes('method not allowed') ||
    message.includes('not found') ||
    message.includes('frontend not built')
  )
}

async function resolveJiraMcpServerName(): Promise<string> {
  const config = await getLivingColorConfigRecord()
  return resolveJiraMcpServer(readMcpServers(config))?.name ?? JIRA_MCP_PRESET_NAME
}

async function persistJiraMcpConfig(serverConfig: Record<string, unknown>): Promise<string> {
  const serverName = await resolveJiraMcpServerName()
  const response = await saveMcpServerConfig(serverName, serverConfig)

  if (!response?.ok) {
    throw new Error('Could not save Jira MCP credentials to config.yaml')
  }

  return response.name ?? serverName
}

function finalizeConnectResponse(result: JiraConnectResponse, saved = false): JiraConnectResponse {
  const connected = Boolean(result.ok)
  let message = result.message || (connected ? 'Connected to Jira via MCP.' : 'Could not connect to Jira.')

  if (!connected && result.message) {
    message = humanizeMcpConnectError(result.message)
  }

  if (saved && !connected) {
    message = `Credentials saved, but the connection failed: ${message}`
  }

  return {
    authenticated: connected,
    message,
    ok: connected,
    saved,
    status: connected ? 'connected' : 'disconnected',
    toolCount: result.toolCount ?? 0
  }
}

function humanizeMcpConnectError(error: string): string {
  if (/streamable_http is not available/i.test(error)) {
    return (
      'The backend is missing MCP HTTP support. Run: pip install "mcp>=1.26.0,<2" ' +
      '(or pip install -e ".[web]"), then quit and reopen LivingColor.'
    )
  }

  if (/npx|enoent|not found.*command|uvx/i.test(error)) {
    return (
      'Node.js (npx) or uv is required for Jira. Install uv from https://docs.astral.sh/uv/ ' +
      'or use “Jira credentials” and ensure uvx is on your PATH.'
    )
  }

  if (/authentication did not complete|oauth token/i.test(error)) {
    return (
      'Atlassian sign-in did not finish. Close any old Atlassian tabs, quit LivingColor, try again, ' +
      'or use “API token” (recommended if you saw “could not identify the application”).'
    )
  }

  if (/500|authorize|oauth|identify the application/i.test(error)) {
    return (
      'Atlassian rejected the OAuth request. Close old sign-in tabs, restart LivingColor, and use ' +
      '“API token” on the dashboard — it is the most reliable option for LivingColor.'
    )
  }

  return error || 'Could not connect to Jira. Try “API token” on the dashboard, then click Connect again.'
}

export function getSampleJiraDashboard(): JiraDashboardPayload {
  return SAMPLE_DASHBOARD
}

export async function loadJiraDashboard(
  requestGateway?: GatewayRequester,
  options: { projectKey?: string | null; reconnect?: boolean } = {}
): Promise<JiraDashboardPayload> {
  const reconnect = options.reconnect ?? false
  const projectKey = options.projectKey ?? null

  // Prefer the dashboard HTTP API — read-only unless the user clicked Refresh.
  try {
    return await fetchJiraDashboard({ projectKey, reconnect })
  } catch (error) {
    if (!isUnavailableRoute(error)) {
      throw error
    }
  }

  if (requestGateway) {
    try {
      return await requestGateway<JiraDashboardPayload>('jira.dashboard', {
        project_key: projectKey,
        reconnect
      })
    } catch (error) {
      if (!isUnavailableRoute(error)) {
        throw error
      }
    }
  }

  return SAMPLE_DASHBOARD
}

export async function connectJiraViaMcp(requestGateway?: GatewayRequester): Promise<JiraConnectResponse> {
  const result = await connectJiraMcp()

  if (requestGateway) {
    await requestGateway('reload.mcp', { confirm: true }).catch(() => undefined)
  }

  return finalizeConnectResponse(result)
}

export async function connectJiraViaCredentials(
  credentials: JiraEnvCredentials,
  requestGateway?: GatewayRequester
): Promise<JiraConnectResponse> {
  const serverConfig = buildJiraMcpAtlassianConfig(credentials)

  await persistJiraMcpConfig(serverConfig)

  const result = await connectJiraMcp()

  if (requestGateway) {
    await requestGateway('reload.mcp', { confirm: true }).catch(() => undefined)
  }

  return finalizeConnectResponse(result, true)
}

/** @deprecated Use connectJiraViaCredentials */
export async function connectJiraViaApiToken(
  email: string,
  apiToken: string,
  requestGateway?: GatewayRequester
): Promise<JiraConnectResponse> {
  return connectJiraViaCredentials(
    { jiraUrl: '', username: email, apiToken },
    requestGateway
  )
}

export async function getJiraSavedCredentials(): Promise<{
  apiToken: string | null
  jiraUrl: string | null
  username: string | null
  usesEnvAuth: boolean
}> {
  const config = await getLivingColorConfigRecord()
  const servers = readMcpServers(config)
  const resolved = resolveJiraMcpServer(servers)

  return readJiraSavedCredentials(resolved?.config ?? servers[JIRA_MCP_PRESET_NAME])
}

export async function resolveJiraBaseUrl(): Promise<string | null> {
  const saved = await getJiraSavedCredentials()
  if (saved.jiraUrl) {
    return saved.jiraUrl
  }

  try {
    const serverName = await resolveJiraMcpServerName()
    const status = await fetchJiraMcpStatus(serverName)
    if (status.jiraUrl) {
      return status.jiraUrl
    }
  } catch {
    // Fall through to dashboard issue URLs.
  }

  try {
    const dashboard = await fetchJiraDashboard({ reconnect: false })
    const issueUrl = dashboard.priorities[0]?.url ?? dashboard.blockers[0]?.url
    if (issueUrl) {
      const match = issueUrl.match(/^(https?:\/\/[^/]+)/i)
      if (match?.[1]) {
        return `${match[1]}/`
      }
    }
  } catch {
    // Ignore — caller renders plain titles when unresolved.
  }

  return null
}

export { JIRA_ATLASSIAN_API_TOKEN_URL }
