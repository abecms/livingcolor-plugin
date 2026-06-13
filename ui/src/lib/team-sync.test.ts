import { beforeEach, describe, expect, it, vi } from 'vitest'

const callCloudApi = vi.fn()
const callDesktopApi = vi.fn()

vi.mock('@/lib/cloud-api', () => ({
  callCloudApi: (...args: unknown[]) => callCloudApi(...args)
}))

vi.mock('@/lib/desktop-api', () => ({
  callDesktopApi: (...args: unknown[]) => callDesktopApi(...args)
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

import { flushPendingEvents, pingCloudHealth } from '@/lib/team-sync'

describe('pingCloudHealth', () => {
  beforeEach(() => {
    callCloudApi.mockReset()
  })

  it('uses the cloud API client (Hermes proxy in dashboard tab)', async () => {
    callCloudApi.mockResolvedValueOnce({ status: 'ok' })
    await expect(pingCloudHealth()).resolves.toBe(true)
    expect(callCloudApi).toHaveBeenCalledWith({ path: '/v1/health', public: true })
  })

  it('returns false when the health probe fails', async () => {
    callCloudApi.mockRejectedValueOnce(new Error('503'))
    await expect(pingCloudHealth()).resolves.toBe(false)
  })
})

describe('flushPendingEvents', () => {
  beforeEach(() => {
    callCloudApi.mockReset()
    callDesktopApi.mockReset()
  })

  it('flushes pending events and marks accepted rows as flushed', async () => {
    callDesktopApi
      .mockResolvedValueOnce({
        orgId: 'team-1',
        events: [{ id: 7, orgId: 'team-1', woId: 'WO-1', payload: { type: 'state_change' }, createdAt: 't' }]
      })
      .mockResolvedValueOnce({ flushed: 1 })
    callCloudApi.mockResolvedValueOnce({ orgId: 'team-1', accepted: [7], conflicts: [] })

    const result = await flushPendingEvents('team-1')

    expect(result.accepted).toEqual([7])
    expect(callCloudApi).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/v1/orgs/team-1/sync/reconcile',
        method: 'POST'
      })
    )
    expect(callDesktopApi).toHaveBeenLastCalledWith(
      expect.objectContaining({
        path: '/api/delivery/cloud/pending-events/mark-flushed',
        method: 'POST',
        body: { ids: [7] }
      })
    )
  })
})
