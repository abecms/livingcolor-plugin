import { afterEach, describe, expect, it } from 'vitest'

import { buildHermesAppPath, HERMES_MCP_SETTINGS_PATH } from './hermes-app-path'

describe('hermes-app-path', () => {
  afterEach(() => {
    delete (window as Window & { __HERMES_BASE_PATH__?: string }).__HERMES_BASE_PATH__
  })

  it('builds MCP settings path at the Hermes host root', () => {
    expect(HERMES_MCP_SETTINGS_PATH).toBe('/mcp')
    expect(buildHermesAppPath(HERMES_MCP_SETTINGS_PATH)).toBe(`${window.location.origin}/mcp`)
  })

  it('prefixes paths with the Hermes base path when set', () => {
    ;(window as Window & { __HERMES_BASE_PATH__?: string }).__HERMES_BASE_PATH__ = '/dashboard/'
    expect(buildHermesAppPath('/mcp')).toBe(`${window.location.origin}/dashboard/mcp`)
  })
})
