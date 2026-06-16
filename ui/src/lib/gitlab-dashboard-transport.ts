import {
  connectGitlabMcp,
  fetchGitlabStatus,
  getLivingColorConfigRecord,
  saveMcpServerConfig,
  testMcpServer
} from '@/hermes'
import type { GitLabConnectResponse } from '@/lib/gitlab-dashboard'
import {
  buildGitLabMcpConfig,
  displayGitLabUrlFromApiUrl,
  GITLAB_MCP_PRESET_NAME,
  normalizeGitLabApiUrl,
  readGitLabSavedCredentials,
  type GitLabEnvCredentials
} from '@/lib/gitlab-mcp'
import { readMcpServers, resolveGitlabMcpServer } from '@/lib/mcp-server-resolver'

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function isMethodNotAllowed(error: unknown): boolean {
  return errorMessage(error).toLowerCase().includes('405')
}

async function resolveGitlabMcpServerName(): Promise<string> {
  const config = await getLivingColorConfigRecord()
  return resolveGitlabMcpServer(readMcpServers(config))?.name ?? GITLAB_MCP_PRESET_NAME
}

async function persistGitLabMcpConfig(serverConfig: Record<string, unknown>): Promise<string> {
  const serverName = await resolveGitlabMcpServerName()
  const response = await saveMcpServerConfig(serverName, serverConfig)

  if (!response?.ok) {
    throw new Error('Could not save GitLab MCP credentials to config.yaml')
  }

  return response.name ?? serverName
}

function finalizeConnectResponse(result: GitLabConnectResponse, saved = false): GitLabConnectResponse {
  const connected = Boolean(result.ok)
  let message = result.message || (connected ? 'Connected to GitLab via MCP.' : 'Could not connect to GitLab.')

  if (saved && !connected) {
    message = `Credentials saved, but the connection failed: ${message}`
  }

  return {
    authenticated: connected,
    gitlabUrl: result.gitlabUrl ?? null,
    message,
    ok: connected,
    saved,
    status: connected ? 'connected' : 'disconnected',
    toolCount: result.toolCount ?? 0
  }
}

async function connectGitlabViaMcpTestFallback(gitlabUrl: string, serverName: string): Promise<GitLabConnectResponse> {
  const result = await testMcpServer(serverName)
  const connected = Boolean(result.ok)
  return {
    authenticated: connected,
    gitlabUrl: displayGitLabUrlFromApiUrl(gitlabUrl) ?? gitlabUrl,
    message: connected
      ? 'Connected to GitLab via MCP.'
      : result.error || 'Could not connect to GitLab. Check the API URL and personal access token.',
    ok: connected,
    status: connected ? 'connected' : 'disconnected',
    toolCount: result.tools?.length ?? 0
  }
}

export async function connectGitlabViaCredentials(credentials: GitLabEnvCredentials): Promise<GitLabConnectResponse> {
  const serverConfig = buildGitLabMcpConfig(credentials)

  const serverName = await persistGitLabMcpConfig(serverConfig)

  try {
    const result = await connectGitlabMcp(serverName)
    return finalizeConnectResponse(result, true)
  } catch (error) {
    if (!isMethodNotAllowed(error)) {
      throw error
    }
    const fallback = await connectGitlabViaMcpTestFallback(normalizeGitLabApiUrl(credentials.gitlabUrl), serverName)
    return finalizeConnectResponse(fallback, true)
  }
}

export async function getGitLabSavedCredentials(): Promise<{
  apiToken: string | null
  gitlabUrl: string | null
  usesEnvAuth: boolean
}> {
  const config = await getLivingColorConfigRecord()
  const servers = readMcpServers(config)
  const resolved = resolveGitlabMcpServer(servers)

  return readGitLabSavedCredentials(resolved?.config ?? servers[GITLAB_MCP_PRESET_NAME])
}

export { fetchGitlabStatus }
