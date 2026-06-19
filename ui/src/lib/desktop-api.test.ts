import { beforeEach, describe, expect, it, vi } from 'vitest'

import { callDesktopApi } from './desktop-api'
import { $firebaseIdToken } from '@/store/firebase-auth'

describe('callDesktopApi', () => {
  beforeEach(() => {
    $firebaseIdToken.set('test-token')
    ;(window as any).__HERMES_PLUGIN_SDK__ = {
      fetchJSON: vi.fn(async () => ({}))
    }
  })

  it('rewrites firebase paths and sends Authorization header', async () => {
    await callDesktopApi({ path: '/api/firebase/bootstrap', method: 'POST' })

    const sdk = (window as any).__HERMES_PLUGIN_SDK__
    expect(sdk.fetchJSON).toHaveBeenCalledTimes(1)
    const [path, init] = sdk.fetchJSON.mock.calls[0]
    expect(path).toBe('/api/plugins/livingcolor/firebase/bootstrap')
    expect(init.method).toBe('POST')
    expect((init.headers as Headers).get('Authorization')).toBe('Bearer test-token')
  })

  it('rewrites plugin settings to the delivery plugin-settings route', async () => {
    await callDesktopApi({ path: '/api/settings', method: 'GET' })

    const sdk = (window as any).__HERMES_PLUGIN_SDK__
    const [path] = sdk.fetchJSON.mock.calls[0]
    expect(path).toBe('/api/plugins/livingcolor/delivery/plugin-settings')
  })

  it('rewrites plugin settings save with PUT', async () => {
    await callDesktopApi({
      path: '/api/settings',
      method: 'PUT',
      body: { billing: { stripeCustomerId: 'cus_test' } }
    })

    const sdk = (window as any).__HERMES_PLUGIN_SDK__
    const [path, init] = sdk.fetchJSON.mock.calls[0]
    expect(path).toBe('/api/plugins/livingcolor/delivery/plugin-settings')
    expect(init.method).toBe('PUT')
  })

  it('rewrites MCP server management paths to the LivingColor plugin', async () => {
    await callDesktopApi({
      path: '/api/mcp/servers/Atlassian',
      method: 'PUT',
      body: { command: 'uvx', args: ['mcp-atlassian'] }
    })

    const sdk = (window as any).__HERMES_PLUGIN_SDK__
    const [path, init] = sdk.fetchJSON.mock.calls[0]
    expect(path).toBe('/api/plugins/livingcolor/mcp/servers/Atlassian')
    expect(init.method).toBe('PUT')
  })
})
