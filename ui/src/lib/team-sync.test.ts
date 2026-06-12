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

import { flushPendingEvents } from '@/lib/team-sync'

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
