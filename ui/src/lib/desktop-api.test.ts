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
})
