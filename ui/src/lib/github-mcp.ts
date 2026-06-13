export const GITHUB_MCP_PRESET_NAME = 'github'
export const GITHUB_PERSONAL_ACCESS_TOKEN_URL = 'https://github.com/settings/tokens'
export const GITHUB_MCP_PACKAGE = '@modelcontextprotocol/server-github'

export interface GitHubEnvCredentials {
  apiToken: string
}

export interface GitHubSavedCredentials {
  apiToken: string | null
  usesEnvAuth: boolean
}

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

export function buildGitHubMcpConfig(credentials: GitHubEnvCredentials): Record<string, unknown> {
  return {
    command: 'npx',
    args: ['-y', GITHUB_MCP_PACKAGE],
    connect_timeout: 120,
    env: {
      GITHUB_TOKEN: credentials.apiToken.trim()
    }
  }
}

export function readGitHubSavedCredentials(
  serverConfig: Record<string, unknown> | undefined
): GitHubSavedCredentials {
  const token = readEnvRecord(serverConfig).GITHUB_TOKEN ?? null
  return token ? { apiToken: token, usesEnvAuth: true } : { apiToken: null, usesEnvAuth: false }
}
