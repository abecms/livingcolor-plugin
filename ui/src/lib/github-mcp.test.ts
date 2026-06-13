import { describe, expect, it } from 'vitest'

import {
  GITHUB_MCP_PACKAGE,
  GITHUB_MCP_PRESET_NAME,
  buildGitHubMcpConfig,
  readGitHubSavedCredentials
} from './github-mcp'

describe('github-mcp', () => {
  it('builds GitHub MCP server config', () => {
    expect(buildGitHubMcpConfig({ apiToken: ' ghp_test ' })).toEqual({
      command: 'npx',
      args: ['-y', GITHUB_MCP_PACKAGE],
      connect_timeout: 120,
      env: { GITHUB_TOKEN: 'ghp_test' }
    })
    expect(GITHUB_MCP_PRESET_NAME).toBe('github')
  })

  it('reads saved GitHub credentials', () => {
    expect(readGitHubSavedCredentials({ env: { GITHUB_TOKEN: 'ghp_saved' } })).toEqual({
      apiToken: 'ghp_saved',
      usesEnvAuth: true
    })
  })
})
