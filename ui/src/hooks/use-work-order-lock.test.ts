import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { $workspaceScope } from '@/store/workspace-scope'

vi.mock('@/lib/work-order-lock-api', () => ({
  acquireWorkOrderLock: vi.fn(async () => ({ orgId: 'team-1', workOrderId: 'WO-1' })),
  releaseWorkOrderLock: vi.fn(async () => ({ orgId: 'team-1', workOrderId: 'WO-1', released: true }))
}))

const subscribeWorkOrderLock = vi.fn(
  async (_orgId: string, _woId: string, onChange: (lock: { holderUid: string; holderEmail: string } | null) => void) => {
    onChange({ holderUid: 'other', holderEmail: 'other@example.com' })
    return () => undefined
  }
)

vi.mock('@/services/firebase-firestore', () => ({
  subscribeWorkOrderLock: (...args: unknown[]) => subscribeWorkOrderLock(...args)
}))

vi.mock('@/services/firebase', () => ({
  getFirebaseAuth: () => ({
    authStateReady: async () => undefined,
    currentUser: { uid: 'me' }
  })
}))

import { useWorkOrderLock } from '@/hooks/use-work-order-lock'

describe('useWorkOrderLock', () => {
  beforeEach(() => {
    subscribeWorkOrderLock.mockClear()
    $workspaceScope.set({ mode: 'local' })
  })

  it('allows writes in local workspace', () => {
    const { result } = renderHook(() => useWorkOrderLock('WO-1'))
    expect(result.current.canWrite).toBe(true)
    expect(result.current.lockMessage).toBeNull()
  })

  it('blocks writes when another member holds the lock', async () => {
    $workspaceScope.set({ mode: 'org', orgId: 'team-1' })
    const { result } = renderHook(() => useWorkOrderLock('WO-1'))
    await waitFor(() => {
      expect(result.current.canWrite).toBe(false)
    })
    expect(result.current.lockMessage).toContain('other@example.com')
  })
})
