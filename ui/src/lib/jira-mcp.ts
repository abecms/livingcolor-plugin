export const JIRA_MCP_PRESET_NAME = 'jira'

/** Atlassian Rovo MCP — authv2 is required for desktop OAuth (legacy /v1/mcp breaks authorize). */
export const JIRA_MCP_URL = 'https://mcp.atlassian.com/v1/mcp/authv2'

/** Standard Atlassian API token page (works with mcp-atlassian). */
export const JIRA_ATLASSIAN_API_TOKEN_URL = 'https://id.atlassian.com/manage-profile/security/api-tokens'

/** MCP-scoped token page for Atlassian Rovo MCP (browser OAuth fallback). */
export const JIRA_ATLASSIAN_ROVO_TOKEN_URL =
  'https://id.atlassian.com/manage-profile/security/api-tokens?autofillToken&expiryDays=max&appId=mcp&selectedScopes=all'

export const JIRA_MCP_ATLASSIAN_PACKAGE = 'mcp-atlassian'

export interface JiraEnvCredentials {
  jiraUrl: string
  username: string
  apiToken: string
}

export interface JiraSavedCredentials {
  apiToken: string | null
  jiraUrl: string | null
  username: string | null
  usesEnvAuth: boolean
}

/**
 * Official Atlassian desktop path: mcp-remote owns OAuth (PKCE + callback) and persists
 * tokens under ~/.config/mcp-remote-*. Direct HTTP OAuth often yields Atlassian
 * "could not identify the application" / 500 authorize errors.
 */
export const JIRA_MCP_STDIO_PRESET_CONFIG = {
  command: 'npx',
  args: ['-y', 'mcp-remote@latest', JIRA_MCP_URL],
  connect_timeout: 300
} satisfies Record<string, unknown>

/** @deprecated Prefer JIRA_MCP_STDIO_PRESET_CONFIG for OAuth; kept for settings imports. */
export const JIRA_MCP_OAUTH_PRESET_CONFIG = {
  url: JIRA_MCP_URL,
  auth: 'oauth',
  connect_timeout: 300,
  oauth: {
    client_name: 'MCP CLI Proxy'
  }
} satisfies Record<string, unknown>

/** @deprecated Use JIRA_MCP_STDIO_PRESET_CONFIG — kept for imports that expect the old name. */
export const JIRA_MCP_PRESET_CONFIG = JIRA_MCP_STDIO_PRESET_CONFIG

function readEnvRecord(serverConfig: Record<string, unknown> | undefined): Record<string, string> {
  const env = serverConfig?.env

  if (!env || typeof env !== 'object' || Array.isArray(env)) {
    return {}
  }

  const out: Record<string, string> = {}

  for (const [key, value] of Object.entries(env as Record<string, unknown>)) {
    if (typeof value === 'string' && value.trim()) {
      out[key] = value.trim()
    }
  }

  return out
}

function readAuthorizationHeader(serverConfig: Record<string, unknown> | undefined): string {
  const headers = serverConfig?.headers

  if (!headers || typeof headers !== 'object' || Array.isArray(headers)) {
    return ''
  }

  for (const [key, value] of Object.entries(headers as Record<string, unknown>)) {
    if (key.toLowerCase() === 'authorization' && typeof value === 'string') {
      return value.trim()
    }
  }

  return ''
}

export function normalizeJiraUrl(url: string): string {
  const trimmed = url.trim()

  if (!trimmed) {
    return ''
  }

  const withProtocol = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`

  return withProtocol.endsWith('/') ? withProtocol : `${withProtocol}/`
}

export function buildJiraIssueBrowseUrl(
  jiraKey: string,
  jiraBaseUrl: string | null | undefined
): string | null {
  const key = jiraKey.trim()
  const base = normalizeJiraUrl(jiraBaseUrl ?? '')

  if (!key || !base) {
    return null
  }

  return `${base.replace(/\/+$/, '')}/browse/${encodeURIComponent(key)}`
}

/** Build the mcp-atlassian stdio preset (same shape as Cursor MCP). */
export function buildJiraMcpAtlassianConfig(credentials: JiraEnvCredentials): Record<string, unknown> {
  return {
    command: 'uvx',
    args: [JIRA_MCP_ATLASSIAN_PACKAGE],
    connect_timeout: 120,
    env: {
      JIRA_URL: normalizeJiraUrl(credentials.jiraUrl),
      JIRA_USERNAME: credentials.username.trim(),
      JIRA_API_TOKEN: credentials.apiToken.trim()
    }
  }
}

/** @deprecated Legacy Rovo MCP HTTP preset — prefer buildJiraMcpAtlassianConfig. */
export function buildJiraApiTokenConfig(email: string, apiToken: string): Record<string, unknown> {
  const credentials = `${email.trim()}:${apiToken.trim()}`

  return {
    url: JIRA_MCP_URL,
    connect_timeout: 120,
    headers: {
      Authorization: `Basic ${btoa(credentials)}`
    }
  }
}

export function readJiraSavedCredentials(
  serverConfig: Record<string, unknown> | undefined
): JiraSavedCredentials {
  const env = readEnvRecord(serverConfig)
  const jiraUrl = env.JIRA_URL ?? null
  const username = env.JIRA_USERNAME ?? null
  const apiToken = env.JIRA_API_TOKEN ?? null

  if (jiraUrl && username) {
    return { apiToken, jiraUrl, username, usesEnvAuth: true }
  }

  const authorization = readAuthorizationHeader(serverConfig)

  if (authorization.toLowerCase().startsWith('basic ')) {
    try {
      const decoded = atob(authorization.slice(6).trim())
      const separator = decoded.indexOf(':')

      if (separator > 0) {
        return {
          apiToken: decoded.slice(separator + 1).trim() || null,
          jiraUrl,
          username: decoded.slice(0, separator).trim() || null,
          usesEnvAuth: false
        }
      }
    } catch {
      return { apiToken: null, jiraUrl: null, username: null, usesEnvAuth: false }
    }
  }

  if (jiraUrl) {
    return { apiToken, jiraUrl, username, usesEnvAuth: false }
  }

  return { apiToken: null, jiraUrl: null, username: null, usesEnvAuth: false }
}

/** @deprecated Use readJiraSavedCredentials().username */
export function readJiraApiTokenEmail(serverConfig: Record<string, unknown> | undefined): string | null {
  return readJiraSavedCredentials(serverConfig).username
}

/** @deprecated Use readJiraSavedCredentials().usesEnvAuth */
export function jiraMcpUsesApiToken(serverConfig: Record<string, unknown> | undefined): boolean {
  const saved = readJiraSavedCredentials(serverConfig)

  return saved.usesEnvAuth || Boolean(saved.username)
}
