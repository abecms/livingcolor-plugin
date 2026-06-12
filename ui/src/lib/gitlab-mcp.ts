export const GITLAB_MCP_PRESET_NAME = 'gitlab'

export const GITLAB_DEFAULT_API_URL = 'https://gitlab.com/api/v4'

export const GITLAB_PERSONAL_ACCESS_TOKEN_URL = 'https://gitlab.com/-/user_settings/personal_access_tokens'

export const GITLAB_MCP_PACKAGE = '@modelcontextprotocol/server-gitlab'

export interface GitLabEnvCredentials {
  gitlabUrl: string
  apiToken: string
}

export interface GitLabSavedCredentials {
  apiToken: string | null
  gitlabUrl: string | null
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

export function normalizeGitLabApiUrl(url: string): string {
  const trimmed = url.trim()

  if (!trimmed) {
    return GITLAB_DEFAULT_API_URL
  }

  const withProtocol = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`
  const normalized = withProtocol.replace(/\/+$/, '')

  if (normalized.endsWith('/api/v4')) {
    return `${normalized}/`
  }

  return `${normalized}/api/v4/`
}

export function displayGitLabUrlFromApiUrl(apiUrl: string | null | undefined): string | null {
  if (!apiUrl?.trim()) {
    return null
  }

  return apiUrl.trim().replace(/\/api\/v4\/?$/i, '').replace(/\/+$/, '') || null
}

export function buildGitLabMcpConfig(credentials: GitLabEnvCredentials): Record<string, unknown> {
  return {
    command: 'npx',
    args: ['-y', GITLAB_MCP_PACKAGE],
    connect_timeout: 120,
    env: {
      GITLAB_API_URL: normalizeGitLabApiUrl(credentials.gitlabUrl),
      GITLAB_PERSONAL_ACCESS_TOKEN: credentials.apiToken.trim()
    }
  }
}

export function readGitLabSavedCredentials(
  serverConfig: Record<string, unknown> | undefined
): GitLabSavedCredentials {
  const env = readEnvRecord(serverConfig)
  const apiUrl = env.GITLAB_API_URL ?? null
  const token = env.GITLAB_PERSONAL_ACCESS_TOKEN ?? null

  if (token) {
    return {
      apiToken: token,
      gitlabUrl: displayGitLabUrlFromApiUrl(apiUrl) ?? 'https://gitlab.com',
      usesEnvAuth: true
    }
  }

  return { apiToken: null, gitlabUrl: null, usesEnvAuth: false }
}
