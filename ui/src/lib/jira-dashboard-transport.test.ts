import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/hermes', () => ({
  connectJiraMcp: vi.fn(async () => ({ ok: true, message: 'ok' })),
  getLivingColorConfigRecord: vi.fn(async () => ({ mcp_servers: {} })),
  saveMcpServerConfig: vi.fn(async () => ({ ok: true })),
}))

import { connectJiraViaMcp } from './jira-dashboard-transport'
import { saveMcpServerConfig } from '@/hermes'

describe('connectJiraViaMcp', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('does not auto-save MCP preset without user credentials', async () => {
    await connectJiraViaMcp()
    expect(saveMcpServerConfig).not.toHaveBeenCalled()
  })
})
