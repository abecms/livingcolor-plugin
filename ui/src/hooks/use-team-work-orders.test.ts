import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { WorkOrder } from '@/app/delivery/types'
import { $workspaceScope } from '@/store/workspace-scope'

const subscribeTeamWorkOrders = vi.fn(
  async (_orgId: string, onChange: (items: Array<{ id: string; data: Record<string, unknown> }>) => void) => {
    onChange([
      {
        id: 'WO-REMOTE',
        data: {
          jiraKey: 'LC-9',
          title: 'Remote WO',
          status: 'completed',
          currentStage: 'completed',
          updatedAt: '2026-06-12T12:00:00Z'
        }
      }
    ])
    return () => undefined
  }
)

vi.mock('@/services/firebase-firestore', () => ({
  subscribeTeamWorkOrders: (...args: unknown[]) => subscribeTeamWorkOrders(...args)
}))

import { useTeamWorkOrders } from '@/hooks/use-team-work-orders'

const localWorkOrder: WorkOrder = {
  id: 'WO-LOCAL',
  jiraKey: 'LC-1',
  title: 'Local WO',
  description: '',
  priority: 'medium',
  status: 'running',
  currentStage: 'development',
  confidence: 0.8,
  createdAt: '2026-06-12T10:00:00Z',
  updatedAt: '2026-06-12T10:00:00Z'
}

describe('useTeamWorkOrders', () => {
  beforeEach(() => {
    subscribeTeamWorkOrders.mockClear()
    $workspaceScope.set({ mode: 'local' })
  })

  it('returns local work orders in personal workspace', () => {
    const { result } = renderHook(() => useTeamWorkOrders([localWorkOrder]))
    expect(result.current.source).toBe('local')
    expect(result.current.workOrders).toEqual([localWorkOrder])
  })

  it('merges Firestore work orders with the local cache in org mode', async () => {
    $workspaceScope.set({ mode: 'org', orgId: 'team-1' })
    const { result } = renderHook(() => useTeamWorkOrders([localWorkOrder]))
    await waitFor(() => {
      expect(result.current.workOrders).toHaveLength(2)
    })
    expect(result.current.source).toBe('merged')
    expect(result.current.workOrders.map(item => item.id).sort()).toEqual(['WO-LOCAL', 'WO-REMOTE'])
    expect(subscribeTeamWorkOrders).toHaveBeenCalledWith('team-1', expect.any(Function))
  })
})
