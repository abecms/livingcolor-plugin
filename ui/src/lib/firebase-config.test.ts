import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/firebase-session', () => ({
  fetchFirebaseClientConfig: vi.fn(async () => ({ enabled: false, config: null }))
}))

import {
  getFirebaseConfigSource,
  resetFirebaseWebConfigCache,
  resolveFirebaseWebConfig
} from '@/lib/firebase-config'

describe('resolveFirebaseWebConfig', () => {
  afterEach(() => {
    resetFirebaseWebConfigCache()
    vi.unstubAllEnvs()
  })

  it('falls back to embedded cloud defaults without local admin', async () => {
    vi.stubEnv('VITE_LC_ENABLE_TEAM_AUTH', 'true')
    const config = await resolveFirebaseWebConfig()
    expect(config?.projectId).toBe('livingcolor-app')
    expect(getFirebaseConfigSource()).toBe('cloud-defaults')
  })
})
