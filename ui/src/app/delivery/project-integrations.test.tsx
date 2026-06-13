import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n'
import {
  fetchGithubStatus,
  fetchGitlabStatus,
  fetchJiraDashboard
} from '@/hermes'
import { getLivingColorConfigRecord } from '@/livingcolor'
import { connectGithubViaCredentials, getGitHubSavedCredentials } from '@/lib/github-dashboard-transport'
import { connectGitlabViaCredentials, getGitLabSavedCredentials } from '@/lib/gitlab-dashboard-transport'
import { connectJiraViaCredentials, getJiraSavedCredentials } from '@/lib/jira-dashboard-transport'
import { fetchProjectConfig, saveProjectConfig } from '@/lib/delivery'

import { ProjectIntegrationsSection } from './project-integrations'

vi.mock('@/hooks/use-project-workspace', () => ({
  useProjectWorkspace: () => ({
    activeProjectKey: 'BN'
  })
}))

const baseProjectConfig = {
  projectKey: 'BN',
  projectName: 'Brand New',
  sprintDurationDays: 14,
  sprintCapacityDays: 10,
  communicationLanguage: 'en' as const,
  ticketScope: { statusGroups: ['todo'], assignees: [], includeUnassigned: true, matchMode: 'all' as const },
  configPath: '/tmp/config.yaml',
  integrationBranch: 'develop'
}

vi.mock('@/lib/delivery', () => ({
  setupProjectAutomation: vi.fn().mockResolvedValue({ projectKey: 'BN', warnings: [] }),
  fetchProjectConfig: vi.fn().mockResolvedValue({
    projectKey: 'BN',
    projectName: 'Brand New',
    sprintDurationDays: 14,
    sprintCapacityDays: 10,
    communicationLanguage: 'en',
    ticketScope: { statusGroups: ['todo'], assignees: [], includeUnassigned: true, matchMode: 'all' },
    configPath: '/tmp/config.yaml',
    integrationBranch: 'develop'
  }),
  fetchProjectGitlabRepos: vi.fn().mockResolvedValue({ items: [], defaultRepo: null }),
  fetchProjectVcsRepos: vi.fn().mockResolvedValue({ items: [], defaultRepo: null, provider: 'github' }),
  fetchProjectJiraProjects: vi.fn().mockResolvedValue({ items: [], linkedProjectKey: 'BN' }),
  saveProjectConfig: vi.fn().mockResolvedValue({
    projectKey: 'BN',
    projectName: 'Brand New',
    sprintDurationDays: 14,
    sprintCapacityDays: 10,
    communicationLanguage: 'en',
    ticketScope: { statusGroups: ['todo'], assignees: [], includeUnassigned: true, matchMode: 'all' },
    configPath: '/tmp/config.yaml',
    integrationBranch: 'develop'
  }),
  saveProjectDefaultRepo: vi.fn().mockResolvedValue({ defaultRepo: null }),
  saveProjectIntegrationBranch: vi.fn().mockResolvedValue({ integrationBranch: 'develop' }),
  saveProjectJiraProjectKey: vi.fn().mockResolvedValue({ jiraProjectKey: 'BN' })
}))

vi.mock('@/hermes', () => ({
  connectGithubMcp: vi.fn().mockResolvedValue({ ok: false, status: 'disconnected' }),
  connectGitlabMcp: vi.fn().mockResolvedValue({ ok: false, status: 'disconnected' }),
  connectJiraMcp: vi.fn().mockResolvedValue({ ok: false, status: 'disconnected' }),
  fetchGithubStatus: vi.fn().mockResolvedValue({
    authenticated: false,
    message: 'GitHub MCP is not configured yet.',
    status: 'disconnected',
    toolCount: 0
  }),
  fetchGitlabStatus: vi.fn().mockResolvedValue({
    authenticated: false,
    message: 'GitLab MCP is not configured yet.',
    status: 'disconnected',
    toolCount: 0
  }),
  fetchJiraDashboard: vi.fn().mockResolvedValue({
    connection: { status: 'disconnected' },
    sampleData: true
  })
}))

vi.mock('@/livingcolor', () => ({
  getLivingColorConfigRecord: vi.fn().mockResolvedValue({ mcp_servers: {} })
}))

vi.mock('@/lib/github-dashboard-transport', () => ({
  connectGithubViaCredentials: vi.fn().mockResolvedValue({ ok: true, message: 'Connected to GitHub.' }),
  getGitHubSavedCredentials: vi.fn().mockResolvedValue({ apiToken: null, usesEnvAuth: false })
}))

vi.mock('@/lib/gitlab-dashboard-transport', () => ({
  connectGitlabViaCredentials: vi.fn().mockResolvedValue({ ok: true, message: 'Connected to GitLab.' }),
  getGitLabSavedCredentials: vi.fn().mockResolvedValue({ gitlabUrl: null, usesEnvAuth: false })
}))

vi.mock('@/lib/jira-dashboard-transport', () => ({
  connectJiraViaCredentials: vi.fn().mockResolvedValue({ ok: true, message: 'Connected to Jira.' }),
  getJiraSavedCredentials: vi.fn().mockResolvedValue({ jiraUrl: null, username: null, usesEnvAuth: false })
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

vi.mock('@/store/project-config', () => ({
  bumpProjectConfigRevision: vi.fn()
}))

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn()
  vi.mocked(fetchProjectConfig).mockResolvedValue(baseProjectConfig)
  vi.mocked(saveProjectConfig).mockResolvedValue(baseProjectConfig)
  vi.mocked(getLivingColorConfigRecord).mockResolvedValue({ mcp_servers: {} })
  vi.mocked(getJiraSavedCredentials).mockResolvedValue({ jiraUrl: null, username: null, usesEnvAuth: false })
  vi.mocked(getGitLabSavedCredentials).mockResolvedValue({ gitlabUrl: null, usesEnvAuth: false })
  vi.mocked(getGitHubSavedCredentials).mockResolvedValue({ apiToken: null, usesEnvAuth: false })
  vi.mocked(fetchJiraDashboard).mockResolvedValue({
    connection: { status: 'disconnected' },
    sampleData: true
  })
  vi.mocked(fetchGitlabStatus).mockResolvedValue({
    authenticated: false,
    message: 'GitLab MCP is not configured yet.',
    status: 'disconnected',
    toolCount: 0
  })
  vi.mocked(fetchGithubStatus).mockResolvedValue({
    authenticated: false,
    message: 'GitHub MCP is not configured yet.',
    status: 'disconnected',
    toolCount: 0
  })

  Object.defineProperty(window, 'livingColorDesktop', {
    configurable: true,
    value: {
      touchBackend: vi.fn().mockResolvedValue(undefined)
    }
  })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderSection() {
  return render(
    <I18nProvider configClient={null}>
      <MemoryRouter>
        <ProjectIntegrationsSection />
      </MemoryRouter>
    </I18nProvider>
  )
}

describe('ProjectIntegrationsSection', () => {
  it('shows Jira and GitLab connect actions plus MCP settings link', async () => {
    renderSection()

    expect(await screen.findByText('Integrations')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Connect Jira' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Connect GitLab' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Open MCP settings' }).getAttribute('href')).toBe('/settings?tab=mcp')
  })

  it('shows GitHub controls when project provider is github', async () => {
    vi.mocked(fetchProjectConfig).mockResolvedValue({
      ...baseProjectConfig,
      vcs: 'github'
    })

    renderSection()

    expect(await screen.findByRole('button', { name: 'Connect GitHub' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Connect GitLab' })).toBeNull()
  })

  it('keeps GitLab controls when project provider is omitted', async () => {
    vi.mocked(fetchProjectConfig).mockResolvedValue(baseProjectConfig)

    renderSection()

    expect(await screen.findByRole('button', { name: 'Connect GitLab' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Connect GitHub' })).toBeNull()
  })

  it('opens the Jira credentials dialog', async () => {
    renderSection()
    await screen.findByRole('button', { name: 'Connect Jira' })

    fireEvent.click(screen.getByRole('button', { name: 'Connect Jira' }))

    expect(await screen.findByRole('dialog')).toBeTruthy()
    expect(screen.getByLabelText('JIRA_URL')).toBeTruthy()
  })

  it('opens the GitLab credentials dialog', async () => {
    renderSection()
    await screen.findByRole('button', { name: 'Connect GitLab' })

    fireEvent.click(screen.getByRole('button', { name: 'Connect GitLab' }))

    expect(await screen.findByRole('dialog')).toBeTruthy()
    expect(screen.getByPlaceholderText('https://gitlab.com')).toBeTruthy()
  })

  it('opens the GitHub credentials dialog', async () => {
    vi.mocked(fetchProjectConfig).mockResolvedValue({
      ...baseProjectConfig,
      vcs: 'github'
    })

    renderSection()
    await screen.findByRole('button', { name: 'Connect GitHub' })

    fireEvent.click(screen.getByRole('button', { name: 'Connect GitHub' }))

    expect(await screen.findByRole('dialog')).toBeTruthy()
    expect(screen.getByLabelText('GitHub token')).toBeTruthy()
  })

  it('submits Jira credentials', async () => {
    renderSection()
    await screen.findByRole('button', { name: 'Connect Jira' })
    fireEvent.click(screen.getByRole('button', { name: 'Connect Jira' }))
    await screen.findByRole('dialog')

    fireEvent.change(screen.getByLabelText(/JIRA_URL/i), {
      target: { value: 'https://afp-jira.atlassian.net/' }
    })
    fireEvent.change(screen.getByLabelText(/JIRA_USERNAME/i), {
      target: { value: 'you@company.com' }
    })
    fireEvent.change(screen.getByLabelText(/JIRA_API_TOKEN/i), {
      target: { value: 'secret-token' }
    })
    fireEvent.click(screen.getByRole('button', { name: 'Connect' }))

    await waitFor(() => {
      expect(connectJiraViaCredentials).toHaveBeenCalledWith({
        jiraUrl: 'https://afp-jira.atlassian.net/',
        username: 'you@company.com',
        apiToken: 'secret-token'
      })
    })
  })

  it('submits GitLab credentials', async () => {
    renderSection()
    await screen.findByRole('button', { name: 'Connect GitLab' })
    fireEvent.click(screen.getByRole('button', { name: 'Connect GitLab' }))
    await screen.findByRole('dialog')

    fireEvent.change(screen.getByPlaceholderText('https://gitlab.com'), {
      target: { value: 'https://gitlab.example.com' }
    })
    fireEvent.change(screen.getByPlaceholderText('glpat-...'), {
      target: { value: 'secret-token' }
    })
    fireEvent.click(screen.getByRole('button', { name: 'Connect' }))

    await waitFor(() => {
      expect(connectGitlabViaCredentials).toHaveBeenCalledWith({
        gitlabUrl: 'https://gitlab.example.com',
        apiToken: 'secret-token'
      })
    })
  })

  it('submits GitHub credentials', async () => {
    vi.mocked(fetchProjectConfig).mockResolvedValue({
      ...baseProjectConfig,
      vcs: 'github'
    })

    renderSection()
    await screen.findByRole('button', { name: 'Connect GitHub' })
    fireEvent.click(screen.getByRole('button', { name: 'Connect GitHub' }))
    await screen.findByRole('dialog')

    fireEvent.change(screen.getByLabelText('GitHub token'), {
      target: { value: 'ghp_secret-token' }
    })
    fireEvent.click(screen.getByRole('button', { name: 'Connect' }))

    await waitFor(() => {
      expect(connectGithubViaCredentials).toHaveBeenCalledWith({
        apiToken: 'ghp_secret-token'
      })
    })
  })

  it('detects an existing Jira MCP entry', async () => {
    vi.mocked(getLivingColorConfigRecord).mockResolvedValueOnce({
      mcp_servers: {
        jira: { command: 'uvx', args: ['mcp-atlassian'] }
      }
    } as never)
    vi.mocked(getJiraSavedCredentials).mockResolvedValueOnce({
      apiToken: null,
      jiraUrl: 'https://afp-jira.atlassian.net/',
      username: 'you@company.com',
      usesEnvAuth: false
    })

    renderSection()

    expect(
      await screen.findByText(/Credentials saved for https:\/\/afp-jira.atlassian.net\//)
    ).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Update Jira credentials' })).toBeTruthy()
  })

  it('detects an existing GitLab MCP entry', async () => {
    vi.mocked(getLivingColorConfigRecord).mockResolvedValueOnce({
      mcp_servers: {
        gitlab: { command: 'npx', args: ['@modelcontextprotocol/server-gitlab'] }
      }
    } as never)
    vi.mocked(getGitLabSavedCredentials).mockResolvedValueOnce({
      apiToken: null,
      gitlabUrl: 'https://gitlab.example.com',
      usesEnvAuth: true
    })

    renderSection()

    expect(await screen.findByText(/Credentials saved for https:\/\/gitlab.example.com/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Update GitLab credentials' })).toBeTruthy()
  })

  it('shows a live connected status when the backend session is active', async () => {
    vi.mocked(fetchJiraDashboard).mockResolvedValueOnce({
      connection: { status: 'connected' },
      sampleData: false
    } as never)
    vi.mocked(fetchGitlabStatus).mockResolvedValueOnce({
      authenticated: true,
      message: 'Connected to GitLab via MCP.',
      status: 'connected',
      toolCount: 9
    } as never)
    vi.mocked(getLivingColorConfigRecord).mockResolvedValueOnce({
      mcp_servers: {
        gitlab: { command: 'npx', args: ['@modelcontextprotocol/server-gitlab'] },
        jira: { command: 'uvx', args: ['mcp-atlassian'] }
      }
    } as never)
    vi.mocked(getJiraSavedCredentials).mockResolvedValueOnce({
      apiToken: null,
      jiraUrl: 'https://afp-jira.atlassian.net/',
      username: 'you@company.com',
      usesEnvAuth: false
    })
    vi.mocked(getGitLabSavedCredentials).mockResolvedValueOnce({
      apiToken: null,
      gitlabUrl: 'https://gitlab.example.com',
      usesEnvAuth: true
    })

    renderSection()

    expect(await screen.findByText(/Connected to https:\/\/afp-jira.atlassian.net\//)).toBeTruthy()
    expect(screen.getByText(/Connected to https:\/\/gitlab.example.com/)).toBeTruthy()
    expect(screen.getAllByRole('button', { name: 'Connected' })).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Update Jira credentials' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Update GitLab credentials' })).toBeTruthy()
  })
})
