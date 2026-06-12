import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchProjectConfig, saveProjectConfig } from '@/lib/delivery'

import { ProjectSettingsView } from './project-settings-view'

vi.mock('@/hooks/use-project-workspace', () => ({
  useProjectWorkspace: () => ({
    activeProjectKey: 'BN',
    activeProject: { jiraProjectKey: 'BN', projectName: 'Bibliothèque Numérique' },
    deleteProject: vi.fn()
  })
}))

vi.mock('@/lib/delivery', () => ({
  DEFAULT_TICKET_SCOPE: {
    statusGroups: ['todo'],
    assignees: [],
    includeUnassigned: true,
    matchMode: 'all'
  },
  fetchProjectConfig: vi.fn().mockResolvedValue({
    projectKey: 'BN',
    projectName: 'Bibliothèque Numérique',
    sprintDurationDays: 14,
    sprintCapacityDays: 15,
    communicationLanguage: 'fr',
    ticketScope: {
      statusGroups: ['todo'],
      assignees: [],
      includeUnassigned: true,
      matchMode: 'all'
    },
    configPath: '/tmp/delivery.yaml'
  }),
  saveProjectConfig: vi.fn().mockResolvedValue({
    projectKey: 'BN',
    projectName: 'Bibliothèque Numérique',
    sprintDurationDays: 21,
    sprintCapacityDays: 18,
    communicationLanguage: 'en',
    ticketScope: {
      statusGroups: ['todo'],
      assignees: [],
      includeUnassigned: true,
      matchMode: 'all'
    },
    configPath: '/tmp/delivery.yaml'
  })
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

afterEach(() => {
  cleanup()
})

describe('ProjectSettingsView', () => {
  it('loads and displays BN sprint settings', async () => {
    render(
      <MemoryRouter initialEntries={['/projects/BN/settings']}>
        <ProjectSettingsView />
      </MemoryRouter>
    )

    expect(await screen.findByRole('heading', { name: 'Project Settings' })).toBeTruthy()
    expect((screen.getByLabelText('Sprint duration (days)') as HTMLInputElement).value).toBe('14')
    expect((screen.getByLabelText('Capacity (person-days)') as HTMLInputElement).value).toBe('15')
    expect(fetchProjectConfig).toHaveBeenCalled()
  })

  it('saves updated sprint settings', async () => {
    render(
      <MemoryRouter initialEntries={['/projects/BN/settings']}>
        <ProjectSettingsView />
      </MemoryRouter>
    )
    await screen.findByRole('heading', { name: 'Project Settings' })

    fireEvent.change(screen.getByLabelText('Sprint duration (days)'), { target: { value: '21' } })
    fireEvent.change(screen.getByLabelText('Capacity (person-days)'), { target: { value: '18' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }))

    await waitFor(() => {
      expect(saveProjectConfig).toHaveBeenCalledWith({
        sprintDurationDays: 21,
        sprintCapacityDays: 18,
        communicationLanguage: 'fr',
        ticketScope: {
          statusGroups: ['todo'],
          assignees: [],
          includeUnassigned: true,
          matchMode: 'all'
        }
      })
    })
  })

  it('loads communication language options', async () => {
    render(
      <MemoryRouter initialEntries={['/projects/BN/settings']}>
        <ProjectSettingsView />
      </MemoryRouter>
    )
    await screen.findByRole('heading', { name: 'Project Settings' })
    expect(screen.getByLabelText('Communication language')).toBeTruthy()
  })
})
