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
import { readMcpServers, resolveGithubMcpServer } from '@/lib/mcp-server-resolver'

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function isMethodNotAllowed(error: unknown): boolean {
  return errorMessage(error).toLowerCase().includes('405')
}

async function resolveGithubMcpServerName(): Promise<string> {
  const config = await getLivingColorConfigRecord()
  return resolveGithubMcpServer(readMcpServers(config))?.name ?? GITHUB_MCP_PRESET_NAME
}

async function persistGitHubMcpConfig(serverConfig: Record<string, unknown>): Promise<string> {
  const serverName = await resolveGithubMcpServerName()
  const response = await saveMcpServerConfig(serverName, serverConfig)

  if (!response?.ok) {
    throw new Error('Could not save GitHub MCP credentials to config.yaml')
  }

  return response.name ?? serverName
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

async function connectGithubViaMcpTestFallback(serverName: string): Promise<GitHubConnectResponse> {
  const result = await testMcpServer(serverName)
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

  const serverName = await persistGitHubMcpConfig(serverConfig)

  try {
    const result = await connectGithubMcp(serverName)
    return finalizeConnectResponse(result, true)
  } catch (error) {
    if (!isMethodNotAllowed(error)) {
      throw error
    }
    const fallback = await connectGithubViaMcpTestFallback(serverName)
    return finalizeConnectResponse(fallback, true)
  }
}

export async function getGitHubSavedCredentials(): Promise<{
  apiToken: string | null
  usesEnvAuth: boolean
}> {
  const config = await getLivingColorConfigRecord()
  const servers = readMcpServers(config)
  const resolved = resolveGithubMcpServer(servers)

  return readGitHubSavedCredentials(resolved?.config ?? servers[GITHUB_MCP_PRESET_NAME])
}

export { fetchGithubStatus }
