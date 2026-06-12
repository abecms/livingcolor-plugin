import { beforeEach, describe, expect, it, vi } from 'vitest'

import { $firebaseActiveOrgId, $firebaseIdToken } from '@/store/firebase-auth'

vi.stubGlobal(
  'fetch',
  vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }))
)

import { callCloudApi, LIVINGCOLOR_CLOUD_API_URL } from '@/lib/cloud-api'

describe('callCloudApi', () => {
  beforeEach(() => {
    vi.mocked(fetch).mockClear()
    $firebaseIdToken.set('tok')
    $firebaseActiveOrgId.set('org-1')
  })

  it('calls api-livingcolor.visualq.ai with auth headers', async () => {
    expect(LIVINGCOLOR_CLOUD_API_URL).toBe('https://api-livingcolor.visualq.ai')
    await callCloudApi({ path: '/v1/session/bootstrap', method: 'POST' })
    const [url, init] = vi.mocked(fetch).mock.calls[0]
    expect(url).toBe('https://api-livingcolor.visualq.ai/v1/session/bootstrap')
    expect((init as RequestInit).headers).toMatchObject({
      Authorization: 'Bearer tok',
      'X-LC-Org-Id': 'org-1'
    })
  })

  it('skips Authorization for public routes', async () => {
    await callCloudApi({ path: '/v1/config/firebase-client', public: true })
    const [, init] = vi.mocked(fetch).mock.calls[0]
    const headers = (init as RequestInit).headers as Record<string, string>
    expect(headers.Authorization).toBeUndefined()
  })
})
