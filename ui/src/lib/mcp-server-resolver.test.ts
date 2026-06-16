import { describe, expect, it } from 'vitest'

import {
  resolveGitlabMcpServer,
  resolveJiraMcpServer,
  readMcpServers
} from './mcp-server-resolver'

describe('mcp-server-resolver', () => {
  it('detects Jira servers configured under custom Hermes names', () => {
    const servers = readMcpServers({
      mcp_servers: {
        Atlassian: {
          command: 'uvx',
          args: ['mcp-atlassian'],
          env: {
            JIRA_URL: 'https://example.atlassian.net/',
            JIRA_USERNAME: 'user@example.com',
            JIRA_API_TOKEN: 'secret'
          }
        }
      }
    })

    expect(resolveJiraMcpServer(servers)).toEqual({
      name: 'Atlassian',
      config: servers.Atlassian
    })
  })

  it('detects GitLab servers configured under custom Hermes names', () => {
    const servers = readMcpServers({
      mcp_servers: {
        'gitlab-tv5': {
          command: 'npx',
          args: ['-y', '@modelcontextprotocol/server-gitlab'],
          env: {
            GITLAB_API_URL: 'https://gitlab.com/api/v4/',
            GITLAB_PERSONAL_ACCESS_TOKEN: 'secret'
          }
        }
      }
    })

    expect(resolveGitlabMcpServer(servers)).toEqual({
      name: 'gitlab-tv5',
      config: servers['gitlab-tv5']
    })
  })
})
