import { beforeEach, describe, expect, it, vi } from 'vitest'

import { callDesktopApi } from './desktop-api'
import {
  fetchProjectConfig,
  fetchProjectVcsRepos,
  saveProjectConfig,
  saveProjectDefaultRepo
} from './delivery'

vi.mock('./desktop-api', () => ({
  callDesktopApi: vi.fn()
}))

describe('delivery VCS helpers', () => {
  beforeEach(() => {
    vi.mocked(callDesktopApi).mockReset()
  })

  it('fetchProjectVcsRepos calls the provider-aware endpoint', async () => {
    vi.mocked(callDesktopApi).mockResolvedValueOnce({
      items: [{ path: 'github.com/org/app', githubId: 42 }],
      defaultRepo: 'github.com/org/app',
      provider: 'github'
    })

    const payload = await fetchProjectVcsRepos('GH')

    expect(callDesktopApi).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/api/delivery/projects/GH/vcs-repos',
        timeoutMs: 120_000
      })
    )
    expect(payload.provider).toBe('github')
    expect(payload.items[0]?.path).toBe('github.com/org/app')
  })

  it('saveProjectConfig persists vcs provider', async () => {
    vi.mocked(callDesktopApi).mockResolvedValueOnce({
      projectKey: 'GH',
      projectName: 'GitHub App',
      sprintDurationDays: 14,
      sprintCapacityDays: 10,
      communicationLanguage: 'en',
      ticketScope: { statusGroups: ['todo'], assignees: [], includeUnassigned: true, matchMode: 'all' },
      configPath: '/tmp/config.yaml',
      vcs: 'github'
    })

    const config = await saveProjectConfig({
      sprintDurationDays: 14,
      sprintCapacityDays: 10,
      communicationLanguage: 'en',
      vcs: 'github'
    })

    expect(callDesktopApi).toHaveBeenCalledWith(
      expect.objectContaining({
        method: 'PUT',
        path: '/api/delivery/project-config',
        body: expect.objectContaining({ vcs: 'github' })
      })
    )
    expect(config.vcs).toBe('github')
  })

  it('saveProjectDefaultRepo preserves vcs when updating default repo', async () => {
    vi.mocked(callDesktopApi)
      .mockResolvedValueOnce({
        projectKey: 'GH',
        projectName: 'GitHub App',
        sprintDurationDays: 14,
        sprintCapacityDays: 10,
        communicationLanguage: 'en',
        ticketScope: { statusGroups: ['todo'], assignees: [], includeUnassigned: true, matchMode: 'all' },
        configPath: '/tmp/config.yaml',
        vcs: 'github',
        defaultRepo: null
      })
      .mockResolvedValueOnce({
        projectKey: 'GH',
        projectName: 'GitHub App',
        sprintDurationDays: 14,
        sprintCapacityDays: 10,
        communicationLanguage: 'en',
        ticketScope: { statusGroups: ['todo'], assignees: [], includeUnassigned: true, matchMode: 'all' },
        configPath: '/tmp/config.yaml',
        vcs: 'github',
        defaultRepo: 'github.com/org/app'
      })

    await saveProjectDefaultRepo('github.com/org/app')

    expect(callDesktopApi).toHaveBeenLastCalledWith(
      expect.objectContaining({
        method: 'PUT',
        body: expect.objectContaining({
          vcs: 'github',
          defaultRepo: 'github.com/org/app'
        })
      })
    )
  })

  it('fetchProjectConfig exposes vcs from backend payload', async () => {
    vi.mocked(callDesktopApi).mockResolvedValueOnce({
      projectKey: 'BN',
      projectName: 'Brand New',
      sprintDurationDays: 14,
      sprintCapacityDays: 10,
      communicationLanguage: 'en',
      ticketScope: { statusGroups: ['todo'], assignees: [], includeUnassigned: true, matchMode: 'all' },
      configPath: '/tmp/config.yaml'
    })

    const config = await fetchProjectConfig()

    expect(config.vcs).toBeUndefined()
  })
})
