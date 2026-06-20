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

  it('attaches the Hermes dashboard session token when present', async () => {
    ;(window as { __HERMES_SESSION_TOKEN__?: string }).__HERMES_SESSION_TOKEN__ = 'dash-tok'

    await callDesktopApi({ path: '/api/delivery/overview' })

    const sdk = (window as any).__HERMES_PLUGIN_SDK__
    const [, init] = sdk.fetchJSON.mock.calls[0]
    expect((init.headers as Headers).get('X-Hermes-Session-Token')).toBe('dash-tok')
  })

  it('falls back to fetch when sdk.fetchJSON fails with a network error', async () => {
    const sdk = (window as any).__HERMES_PLUGIN_SDK__
    sdk.fetchJSON = vi.fn(async () => {
      throw new Error('Failed to fetch')
    })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    )

    const result = await callDesktopApi<{ ok: boolean }>({ path: '/api/delivery/overview' })

    expect(result).toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    fetchMock.mockRestore()
  })
})
