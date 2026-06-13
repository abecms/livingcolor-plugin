import {
  connectGithubMcp,
  fetchGithubStatus,
  getLivingColorConfigRecord,
  saveMcpServerConfig,
  testMcpServer
} from '@/hermes'
import type { GitHubConnectResponse } from '@/lib/github-dashboard'
import {
  buildGitHubMcpConfig,
  GITHUB_MCP_PRESET_NAME,
  readGitHubSavedCredentials,
  type GitHubEnvCredentials
} from '@/lib/github-mcp'

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function isMethodNotAllowed(error: unknown): boolean {
  return errorMessage(error).toLowerCase().includes('405')
}

async function persistGitHubMcpConfig(serverConfig: Record<string, unknown>): Promise<void> {
  const response = await saveMcpServerConfig(GITHUB_MCP_PRESET_NAME, serverConfig)

  if (!response?.ok) {
    throw new Error('Could not save GitHub MCP credentials to config.yaml')
  }
}

function finalizeConnectResponse(result: GitHubConnectResponse, saved = false): GitHubConnectResponse {
  const connected = Boolean(result.ok)
  let message = result.message || (connected ? 'Connected to GitHub via MCP.' : 'Could not connect to GitHub.')

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

async function connectGithubViaMcpTestFallback(): Promise<GitHubConnectResponse> {
  const result = await testMcpServer(GITHUB_MCP_PRESET_NAME)
  const connected = Boolean(result.ok)
  return {
    authenticated: connected,
    message: connected
      ? 'Connected to GitHub via MCP.'
      : result.error || 'Could not connect to GitHub. Check the personal access token scopes.',
    ok: connected,
    status: connected ? 'connected' : 'disconnected',
    toolCount: result.tools?.length ?? 0
  }
}

export async function connectGithubViaCredentials(credentials: GitHubEnvCredentials): Promise<GitHubConnectResponse> {
  const serverConfig = buildGitHubMcpConfig(credentials)

  await persistGitHubMcpConfig(serverConfig)

  try {
    const result = await connectGithubMcp()
    return finalizeConnectResponse(result, true)
  } catch (error) {
    if (!isMethodNotAllowed(error)) {
      throw error
    }
    const fallback = await connectGithubViaMcpTestFallback()
    return finalizeConnectResponse(fallback, true)
  }
}

export async function getGitHubSavedCredentials(): Promise<{
  apiToken: string | null
  usesEnvAuth: boolean
}> {
  const config = await getLivingColorConfigRecord()
  const currentServers =
    config.mcp_servers && typeof config.mcp_servers === 'object' && !Array.isArray(config.mcp_servers)
      ? (config.mcp_servers as Record<string, Record<string, unknown>>)
      : {}

  return readGitHubSavedCredentials(currentServers[GITHUB_MCP_PRESET_NAME])
}

export { fetchGithubStatus }
