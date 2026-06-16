export const CANONICAL_JIRA_MCP_NAME = 'jira'
export const CANONICAL_GITLAB_MCP_NAME = 'gitlab'
export const CANONICAL_GITHUB_MCP_NAME = 'github'

export type McpServerMap = Record<string, Record<string, unknown>>

function argsBlob(config: Record<string, unknown>): string {
  const args = config.args
  if (!Array.isArray(args)) {
    return ''
  }
  return args.map(value => String(value)).join(' ').toLowerCase()
}

function envKeys(config: Record<string, unknown>): Set<string> {
  const env = config.env
  if (!env || typeof env !== 'object' || Array.isArray(env)) {
    return new Set()
  }
  return new Set(Object.keys(env as Record<string, unknown>).map(key => key.toUpperCase()))
}

export function isJiraMcpServer(name: string, config: Record<string, unknown>): boolean {
  const lowered = name.trim().toLowerCase()
  if (lowered === CANONICAL_JIRA_MCP_NAME || lowered === 'atlassian' || lowered.includes('jira') || lowered.includes('atlassian')) {
    return true
  }
  const args = argsBlob(config)
  if (args.includes('mcp-atlassian')) {
    return true
  }
  if (args.includes('mcp-remote') && args.includes('atlassian')) {
    return true
  }
  const env = envKeys(config)
  return env.has('JIRA_URL') || env.has('JIRA_USERNAME')
}

export function isGitlabMcpServer(name: string, config: Record<string, unknown>): boolean {
  const lowered = name.trim().toLowerCase()
  if (lowered === CANONICAL_GITLAB_MCP_NAME || lowered.includes('gitlab')) {
    return true
  }
  const args = argsBlob(config)
  return (
    args.includes('server-gitlab') ||
    args.includes('@modelcontextprotocol/server-gitlab') ||
    envKeys(config).has('GITLAB_API_URL') ||
    envKeys(config).has('GITLAB_PERSONAL_ACCESS_TOKEN')
  )
}

export function isGithubMcpServer(name: string, config: Record<string, unknown>): boolean {
  const lowered = name.trim().toLowerCase()
  if (lowered === CANONICAL_GITHUB_MCP_NAME || lowered.includes('github')) {
    return true
  }
  const args = argsBlob(config)
  return (
    args.includes('server-github') ||
    args.includes('@modelcontextprotocol/server-github') ||
    envKeys(config).has('GITHUB_PERSONAL_ACCESS_TOKEN')
  )
}

function resolveServerName(
  servers: McpServerMap,
  canonical: string,
  predicate: (name: string, config: Record<string, unknown>) => boolean
): string | null {
  const canonicalConfig = servers[canonical]
  if (canonicalConfig && predicate(canonical, canonicalConfig)) {
    return canonical
  }

  for (const [name, config] of Object.entries(servers)) {
    if (config && predicate(name, config)) {
      return name
    }
  }

  return null
}

export function resolveJiraMcpServer(servers: McpServerMap): { name: string; config: Record<string, unknown> } | null {
  const name = resolveServerName(servers, CANONICAL_JIRA_MCP_NAME, isJiraMcpServer)
  if (!name) {
    return null
  }
  return { name, config: servers[name] ?? {} }
}

export function resolveGitlabMcpServer(servers: McpServerMap): { name: string; config: Record<string, unknown> } | null {
  const name = resolveServerName(servers, CANONICAL_GITLAB_MCP_NAME, isGitlabMcpServer)
  if (!name) {
    return null
  }
  return { name, config: servers[name] ?? {} }
}

export function resolveGithubMcpServer(servers: McpServerMap): { name: string; config: Record<string, unknown> } | null {
  const name = resolveServerName(servers, CANONICAL_GITHUB_MCP_NAME, isGithubMcpServer)
  if (!name) {
    return null
  }
  return { name, config: servers[name] ?? {} }
}

export function readMcpServers(config: { mcp_servers?: unknown } | null | undefined): McpServerMap {
  const servers = config?.mcp_servers
  if (!servers || typeof servers !== 'object' || Array.isArray(servers)) {
    return {}
  }
  return servers as McpServerMap
}
