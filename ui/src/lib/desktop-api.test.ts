import { beforeEach, describe, expect, it, vi } from 'vitest'
import { $firebaseIdToken } from '@/store/firebase-auth'

describe('callDesktopApi', () => {
  beforeEach(() => {
    $firebaseIdToken.set('test-token')
    ;(window as any).__HERMES_PLUGIN_SDK__ = {
      fetchJSON: vi.fn(async () => ({}))
    }
  })

  it('rewrites firebase paths and sends Authorization header', async () => {
    const { callDesktopApi } = await import('./desktop-api')
    await callDesktopApi({ path: '/api/firebase/bootstrap', method: 'POST' })

    const sdk = (window as any).__HERMES_PLUGIN_SDK__
    expect(sdk.fetchJSON).toHaveBeenCalledWith(
      '/api/plugins/livingcolor/firebase/bootstrap',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token'
        })
      })
    )
  })
})
