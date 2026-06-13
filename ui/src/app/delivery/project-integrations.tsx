import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tip } from '@/components/ui/tooltip'
import { useI18n } from '@/i18n'
import { getLivingColorConfigRecord } from '@/livingcolor'
import {
  connectGithubMcp,
  connectGitlabMcp,
  connectJiraMcp,
  fetchGithubStatus,
  fetchGitlabStatus,
  fetchJiraDashboard
} from '@/hermes'
import { connectGithubViaCredentials, getGitHubSavedCredentials } from '@/lib/github-dashboard-transport'
import { connectGitlabViaCredentials, getGitLabSavedCredentials } from '@/lib/gitlab-dashboard-transport'
import { connectJiraViaCredentials, getJiraSavedCredentials } from '@/lib/jira-dashboard-transport'
import {
  setupProjectAutomation,
  fetchProjectConfig,
  fetchProjectGitlabRepos,
  fetchProjectJiraProjects,
  fetchProjectVcsRepos,
  saveProjectConfig,
  saveProjectDefaultRepo,
  saveProjectIntegrationBranch,
  saveProjectJiraProjectKey,
  type GitLabRepoOption,
  type JiraProjectOption,
  type VcsProvider,
  type VcsRepoOption
} from '@/lib/delivery'
import { bumpProjectConfigRevision } from '@/store/project-config'
import { GITHUB_MCP_PRESET_NAME } from '@/lib/github-mcp'
import { GITLAB_MCP_PRESET_NAME } from '@/lib/gitlab-mcp'
import { JIRA_MCP_PRESET_NAME } from '@/lib/jira-mcp'
import { Link2 } from '@/lib/icons'
import { notifyError, notify } from '@/store/notifications'

import { useProjectWorkspace } from '@/hooks/use-project-workspace'

import { ManagerSection } from '../manager-page-layout'
import { SETTINGS_ROUTE } from '../routes'

import { dashboardOutlineButtonProps, dashboardPrimaryButtonProps } from './dashboard-ui'

import { GitHubTokenDialog, type GitHubCredentialsFormValues } from '@/lib/integrations/github-token-dialog'
import { GitLabTokenDialog, type GitLabCredentialsFormValues } from '@/lib/integrations/gitlab-token-dialog'
import { JiraApiTokenDialog, type JiraCredentialsFormValues } from '@/lib/integrations/jira-api-token-dialog'

type IntegrationStatus = 'loading' | 'missing' | 'configured' | 'connected'

function normalizeVcsProvider(value: unknown): VcsProvider {
  return String(value ?? '').trim().toLowerCase() === 'github' ? 'github' : 'gitlab'
}

function buildStatusLabel(input: {
  connectedUrl?: string | null
  missingLabel: string
  offlineConfiguredLabel: string
  offlineGenericLabel: string
  connectedGenericLabel: string
  status: IntegrationStatus
}): string {
  if (input.status === 'loading') {
    return 'Checking connection…'
  }

  if (input.status === 'connected') {
    return input.connectedUrl
      ? `Connected to ${input.connectedUrl}`
      : input.connectedGenericLabel
  }

  if (input.status === 'configured') {
    return input.connectedUrl ? input.offlineConfiguredLabel.replace('{url}', input.connectedUrl) : input.offlineGenericLabel
  }

  return input.missingLabel
}

function integrationConnectLabel(input: {
  connectedLabel: string
  connectLabel: string
  status: IntegrationStatus
  updateLabel: string
}): string {
  if (input.status === 'connected') {
    return input.connectedLabel
  }

  if (input.status === 'configured') {
    return input.updateLabel
  }

  return input.connectLabel
}

export function ProjectIntegrationsSection() {
  const { t } = useI18n()
  const { activeProjectKey } = useProjectWorkspace()
  const [vcsProvider, setVcsProvider] = useState<VcsProvider>('gitlab')
  const [vcsProviderSaving, setVcsProviderSaving] = useState(false)
  const [jiraStatus, setJiraStatus] = useState<IntegrationStatus>('loading')
  const [gitlabStatus, setGitlabStatus] = useState<IntegrationStatus>('loading')
  const [githubStatus, setGithubStatus] = useState<IntegrationStatus>('loading')
  const [jiraDialogOpen, setJiraDialogOpen] = useState(false)
  const [gitlabDialogOpen, setGitlabDialogOpen] = useState(false)
  const [githubDialogOpen, setGithubDialogOpen] = useState(false)
  const [jiraConnecting, setJiraConnecting] = useState(false)
  const [gitlabConnecting, setGitlabConnecting] = useState(false)
  const [githubConnecting, setGithubConnecting] = useState(false)
  const [automationSetupBusy, setAutomationSetupBusy] = useState(false)
  const [defaultRepo, setDefaultRepo] = useState('')
  const [integrationBranch, setIntegrationBranch] = useState('')
  const [vcsRepos, setVcsRepos] = useState<Array<GitLabRepoOption | VcsRepoOption>>([])
  const [linkedJiraProjectKey, setLinkedJiraProjectKey] = useState('')
  const [jiraProjects, setJiraProjects] = useState<JiraProjectOption[]>([])
  const [reposLoading, setReposLoading] = useState(false)
  const [jiraProjectsLoading, setJiraProjectsLoading] = useState(false)
  const [repoSaving, setRepoSaving] = useState(false)
  const [branchSaving, setBranchSaving] = useState(false)
  const [jiraProjectSaving, setJiraProjectSaving] = useState(false)
  const [jiraSavedCredentials, setJiraSavedCredentials] = useState<Partial<JiraCredentialsFormValues>>({})
  const [gitlabSavedCredentials, setGitlabSavedCredentials] = useState<Partial<GitLabCredentialsFormValues>>({})
  const [githubSavedCredentials, setGithubSavedCredentials] = useState<Partial<GitHubCredentialsFormValues>>({})

  const forgeLabel = vcsProvider === 'github' ? 'GitHub' : 'GitLab'
  const reviewRequestLabel = vcsProvider === 'github' ? 'PR' : 'MR'
  const forgeStatus = vcsProvider === 'github' ? githubStatus : gitlabStatus

  const loadProjectVcsProvider = useCallback(async () => {
    try {
      const config = await fetchProjectConfig()
      setVcsProvider(normalizeVcsProvider(config.vcs))
      setIntegrationBranch(config.integrationBranch ?? '')
    } catch (error) {
      notifyError(error, 'Could not load project VCS provider')
      setVcsProvider('gitlab')
    }
  }, [])

  const refreshStatus = useCallback(async () => {
    setJiraStatus('loading')
    setGitlabStatus('loading')
    setGithubStatus('loading')
    try {
      let [config, jiraSaved, gitlabSaved, githubSaved, jiraDashboard, gitlabConnection, githubConnection] =
        await Promise.all([
          getLivingColorConfigRecord(),
          getJiraSavedCredentials(),
          getGitLabSavedCredentials(),
          getGitHubSavedCredentials(),
          fetchJiraDashboard({ reconnect: false }).catch(() => null),
          fetchGitlabStatus().catch(() => null),
          fetchGithubStatus().catch(() => null)
        ])
      const servers =
        config?.mcp_servers && typeof config.mcp_servers === 'object' && !Array.isArray(config.mcp_servers)
          ? (config.mcp_servers as Record<string, Record<string, unknown>>)
          : {}

      const hasJiraServer = Boolean(servers[JIRA_MCP_PRESET_NAME])
      const hasJiraCredentials = Boolean(jiraSaved.jiraUrl && jiraSaved.username) || jiraSaved.usesEnvAuth
      let jiraLiveConnected = jiraDashboard?.connection?.status === 'connected' && jiraDashboard.sampleData !== true

      const hasGitLabServer = Boolean(servers[GITLAB_MCP_PRESET_NAME])
      const hasGitLabCredentials = Boolean(gitlabSaved.gitlabUrl) || gitlabSaved.usesEnvAuth
      let gitlabLiveConnected = gitlabConnection?.status === 'connected' && gitlabConnection.authenticated

      const hasGitHubServer = Boolean(servers[GITHUB_MCP_PRESET_NAME])
      const hasGitHubCredentials = Boolean(githubSaved.apiToken) || githubSaved.usesEnvAuth
      let githubLiveConnected = githubConnection?.status === 'connected' && githubConnection.authenticated

      if ((hasJiraServer || hasJiraCredentials) && !jiraLiveConnected) {
        await connectJiraMcp().catch(() => undefined)
      }
      if ((hasGitLabServer || hasGitLabCredentials) && !gitlabLiveConnected) {
        await connectGitlabMcp().catch(() => undefined)
      }
      if ((hasGitHubServer || hasGitHubCredentials) && !githubLiveConnected) {
        await connectGithubMcp().catch(() => undefined)
      }

      if (
        ((hasJiraServer || hasJiraCredentials) && !jiraLiveConnected) ||
        ((hasGitLabServer || hasGitLabCredentials) && !gitlabLiveConnected) ||
        ((hasGitHubServer || hasGitHubCredentials) && !githubLiveConnected)
      ) {
        ;[jiraDashboard, gitlabConnection, githubConnection] = await Promise.all([
          fetchJiraDashboard({ reconnect: false }).catch(() => null),
          fetchGitlabStatus().catch(() => null),
          fetchGithubStatus().catch(() => null)
        ])
        jiraLiveConnected = jiraDashboard?.connection?.status === 'connected' && jiraDashboard.sampleData !== true
        gitlabLiveConnected = gitlabConnection?.status === 'connected' && gitlabConnection.authenticated
        githubLiveConnected = githubConnection?.status === 'connected' && githubConnection.authenticated
      }

      setJiraSavedCredentials({
        apiToken: jiraSaved.apiToken ?? undefined,
        jiraUrl: jiraSaved.jiraUrl ?? undefined,
        username: jiraSaved.username ?? undefined
      })
      if (jiraLiveConnected) {
        setJiraStatus('connected')
      } else if (hasJiraServer || hasJiraCredentials) {
        setJiraStatus('configured')
      } else {
        setJiraStatus('missing')
      }

      setGitlabSavedCredentials({
        apiToken: gitlabSaved.apiToken ?? undefined,
        gitlabUrl: gitlabSaved.gitlabUrl ?? undefined
      })
      if (gitlabLiveConnected) {
        setGitlabStatus('connected')
      } else if (hasGitLabServer || hasGitLabCredentials) {
        setGitlabStatus('configured')
      } else {
        setGitlabStatus('missing')
      }

      setGithubSavedCredentials({
        apiToken: githubSaved.apiToken ?? undefined
      })
      if (githubLiveConnected) {
        setGithubStatus('connected')
      } else if (hasGitHubServer || hasGitHubCredentials) {
        setGithubStatus('configured')
      } else {
        setGithubStatus('missing')
      }
    } catch (error) {
      notifyError(error, 'Could not load integration status')
      setJiraStatus('missing')
      setGitlabStatus('missing')
      setGithubStatus('missing')
    }
  }, [])

  const fetchVcsRepoOptions = useCallback(async () => {
    if (!activeProjectKey) {
      return
    }

    setReposLoading(true)
    try {
      const [config] = await Promise.all([fetchProjectConfig()])
      const provider = normalizeVcsProvider(config.vcs)
      const reposPayload =
        provider === 'github'
          ? await fetchProjectVcsRepos(activeProjectKey)
          : await fetchProjectGitlabRepos(activeProjectKey)
      setVcsRepos(reposPayload.items ?? [])
      setDefaultRepo(reposPayload.defaultRepo ?? '')
      setIntegrationBranch(config.integrationBranch ?? '')
    } catch (error) {
      notifyError(error, `Could not load ${forgeLabel} repositories`)
      setVcsRepos([])
    } finally {
      setReposLoading(false)
    }
  }, [activeProjectKey, forgeLabel])

  const fetchJiraProjectOptions = useCallback(async () => {
    if (!activeProjectKey) {
      return
    }

    setJiraProjectsLoading(true)
    try {
      const payload = await fetchProjectJiraProjects(activeProjectKey)
      setJiraProjects(payload.items ?? [])
      setLinkedJiraProjectKey(payload.linkedProjectKey ?? activeProjectKey)
    } catch (error) {
      notifyError(error, 'Could not load Jira projects')
      setJiraProjects([])
      setLinkedJiraProjectKey(activeProjectKey)
    } finally {
      setJiraProjectsLoading(false)
    }
  }, [activeProjectKey])

  const loadVcsRepos = useCallback(async () => {
    if (!activeProjectKey || forgeStatus !== 'connected') {
      setVcsRepos([])
      setDefaultRepo('')
      return
    }

    await fetchVcsRepoOptions()
  }, [activeProjectKey, fetchVcsRepoOptions, forgeStatus])

  useEffect(() => {
    void loadProjectVcsProvider()
    void refreshStatus()
  }, [activeProjectKey, loadProjectVcsProvider, refreshStatus])

  useEffect(() => {
    void loadVcsRepos()
  }, [loadVcsRepos, vcsProvider])

  const loadJiraProjects = useCallback(async () => {
    if (!activeProjectKey || jiraStatus !== 'connected') {
      setJiraProjects([])
      setLinkedJiraProjectKey(activeProjectKey ?? '')
      return
    }

    await fetchJiraProjectOptions()
  }, [activeProjectKey, fetchJiraProjectOptions, jiraStatus])

  useEffect(() => {
    void loadJiraProjects()
  }, [loadJiraProjects])

  const openConnectDialog = useCallback(
    async (target: 'jira' | 'gitlab' | 'github') => {
      try {
        await window.livingColorDesktop?.touchBackend?.()
        await refreshStatus()
        if (target === 'jira') {
          setJiraDialogOpen(true)
        } else if (target === 'github') {
          setGithubDialogOpen(true)
        } else {
          setGitlabDialogOpen(true)
        }
      } catch (error) {
        notifyError(error, 'LivingColor backend is not ready yet')
      }
    },
    [refreshStatus]
  )

  const handleVcsProviderChange = useCallback(
    async (nextProvider: VcsProvider) => {
      if (nextProvider === vcsProvider || vcsProviderSaving) {
        return
      }

      setVcsProviderSaving(true)
      setVcsProvider(nextProvider)
      try {
        const config = await fetchProjectConfig()
        await saveProjectConfig({
          sprintDurationDays: config.sprintDurationDays,
          sprintCapacityDays: config.sprintCapacityDays,
          communicationLanguage: config.communicationLanguage === 'en' ? 'en' : 'fr',
          ticketScope: config.ticketScope,
          vcs: nextProvider,
          defaultRepo: config.defaultRepo,
          integrationBranch: config.integrationBranch,
          jiraProjectKey: config.jiraProjectKey
        })
        bumpProjectConfigRevision()
        setVcsRepos([])
        setDefaultRepo('')
        await loadVcsRepos()
      } catch (error) {
        setVcsProvider(vcsProvider)
        notifyError(error, 'Could not save VCS provider')
      } finally {
        setVcsProviderSaving(false)
      }
    },
    [loadVcsRepos, vcsProvider, vcsProviderSaving]
  )

  const handleJiraConnect = useCallback(
    async (values: JiraCredentialsFormValues) => {
      setJiraConnecting(true)
      try {
        const result = await connectJiraViaCredentials(values)
        if (!result.ok) {
          notifyError(new Error(result.message || 'Could not connect to Jira'), 'Jira connection failed')
          return false
        }
        notify({ kind: 'success', message: result.message || 'Connected to Jira.' })
        await refreshStatus()
        await fetchJiraProjectOptions()
        return true
      } catch (error) {
        notifyError(error, 'Jira connection failed')
        return false
      } finally {
        setJiraConnecting(false)
      }
    },
    [fetchJiraProjectOptions, refreshStatus]
  )

  const handleGitlabConnect = useCallback(
    async (values: GitLabCredentialsFormValues) => {
      setGitlabConnecting(true)
      try {
        const result = await connectGitlabViaCredentials(values)
        if (!result.ok) {
          notifyError(new Error(result.message || 'Could not connect to GitLab'), 'GitLab connection failed')
          return false
        }
        notify({ kind: 'success', message: result.message || 'Connected to GitLab.' })
        await refreshStatus()
        await fetchVcsRepoOptions()
        return true
      } catch (error) {
        notifyError(error, 'GitLab connection failed')
        return false
      } finally {
        setGitlabConnecting(false)
      }
    },
    [fetchVcsRepoOptions, refreshStatus]
  )

  const handleGithubConnect = useCallback(
    async (values: GitHubCredentialsFormValues) => {
      setGithubConnecting(true)
      try {
        const result = await connectGithubViaCredentials(values)
        if (!result.ok) {
          notifyError(new Error(result.message || 'Could not connect to GitHub'), 'GitHub connection failed')
          return false
        }
        notify({ kind: 'success', message: result.message || 'Connected to GitHub.' })
        await refreshStatus()
        await fetchVcsRepoOptions()
        return true
      } catch (error) {
        notifyError(error, 'GitHub connection failed')
        return false
      } finally {
        setGithubConnecting(false)
      }
    },
    [fetchVcsRepoOptions, refreshStatus]
  )

  const handleDefaultRepoChange = useCallback(
    async (repoPath: string) => {
      setDefaultRepo(repoPath)
      if (!repoPath.trim()) {
        return
      }

      setRepoSaving(true)
      try {
        await saveProjectDefaultRepo(repoPath.trim())
        notify({ kind: 'success', message: t.delivery.projectIntegrations.targetRepoSaved })
      } catch (error) {
        notifyError(error, 'Could not save target repository')
      } finally {
        setRepoSaving(false)
      }
    },
    [t]
  )

  const handleIntegrationBranchSave = useCallback(async () => {
    const branch = integrationBranch.trim()
    if (!branch) {
      return
    }

    setBranchSaving(true)
    try {
      const config = await saveProjectIntegrationBranch(branch)
      setIntegrationBranch(config.integrationBranch ?? branch)
      notify({ kind: 'success', message: t.delivery.projectIntegrations.mergeTargetSaved })
    } catch (error) {
      notifyError(error, 'Could not save integration branch')
    } finally {
      setBranchSaving(false)
    }
  }, [integrationBranch, t])

  const handleLinkedJiraProjectChange = useCallback(
    async (jiraProjectKey: string) => {
      setLinkedJiraProjectKey(jiraProjectKey)
      if (!jiraProjectKey.trim()) {
        return
      }

      setJiraProjectSaving(true)
      try {
        await saveProjectJiraProjectKey(jiraProjectKey.trim())
        bumpProjectConfigRevision()
        notify({ kind: 'success', message: t.delivery.projectIntegrations.targetJiraSaved })
      } catch (error) {
        notifyError(error, 'Could not save linked Jira project')
      } finally {
        setJiraProjectSaving(false)
      }
    },
    [t]
  )

  const automationPrerequisitesMet = jiraStatus === 'connected' && forgeStatus === 'connected'
  const linkedJiraProjectLabel = linkedJiraProjectKey || activeProjectKey || 'this project'

  const automationDisabledTooltip = useMemo(() => {
    if (automationPrerequisitesMet) {
      return null
    }

    const missing: string[] = []
    if (jiraStatus !== 'connected') {
      missing.push(t.delivery.projectIntegrations.missingPrerequisiteJira)
    }
    if (forgeStatus !== 'connected') {
      missing.push(
        vcsProvider === 'github'
          ? t.delivery.projectIntegrations.missingPrerequisiteGitHub
          : t.delivery.projectIntegrations.missingPrerequisiteGitLab
      )
    }

    if (missing.length === 0) {
      return null
    }

    return t.delivery.projectIntegrations.setupAutomationDisabledTooltip(missing.join(', '))
  }, [automationPrerequisitesMet, forgeStatus, jiraStatus, t, vcsProvider])

  const handleSetupAutomation = useCallback(async () => {
    if (!activeProjectKey || !automationPrerequisitesMet || automationSetupBusy) {
      return
    }

    setAutomationSetupBusy(true)
    try {
      const result = await setupProjectAutomation(activeProjectKey)
      notify({
        kind: 'success',
        message: t.delivery.projectIntegrations.setupAutomationSuccess(result.projectKey)
      })
      if (result.warnings.length) {
        notify({ kind: 'warning', message: result.warnings.join(' ') })
      }
    } catch (error) {
      notifyError(error, 'Project automation setup failed')
    } finally {
      setAutomationSetupBusy(false)
    }
  }, [activeProjectKey, automationPrerequisitesMet, automationSetupBusy, t])

  const jiraStatusLabel = buildStatusLabel({
    connectedGenericLabel: 'Connected to Jira via MCP',
    connectedUrl: jiraSavedCredentials.jiraUrl,
    missingLabel: 'Jira MCP is not configured yet',
    offlineConfiguredLabel:
      'Credentials saved for {url}, but the backend session is offline. Reconnect Jira before running daily analysis.',
    offlineGenericLabel:
      'Jira MCP configured, but not connected in the LivingColor backend. Reconnect before running daily analysis.',
    status: jiraStatus
  })

  const gitlabStatusLabel = buildStatusLabel({
    connectedGenericLabel: 'Connected to GitLab via MCP',
    connectedUrl: gitlabSavedCredentials.gitlabUrl,
    missingLabel: 'GitLab MCP is not configured yet',
    offlineConfiguredLabel:
      'Credentials saved for {url}, but the backend session is offline. Reconnect GitLab before MR drafts and repo workflows.',
    offlineGenericLabel:
      'GitLab MCP configured, but not connected in the LivingColor backend. Reconnect before MR drafts and repo workflows.',
    status: gitlabStatus
  })

  const githubStatusLabel = buildStatusLabel({
    connectedGenericLabel: 'Connected to GitHub via MCP',
    connectedUrl: null,
    missingLabel: 'GitHub MCP is not configured yet',
    offlineConfiguredLabel:
      'Credentials saved, but the backend session is offline. Reconnect GitHub before PR drafts and repo workflows.',
    offlineGenericLabel:
      'GitHub MCP configured, but not connected in the LivingColor backend. Reconnect before PR drafts and repo workflows.',
    status: githubStatus
  })

  const renderForgeRepoSettings = () => (
    <div className="mt-5 space-y-3 border-t border-(--ui-border-subtle) pt-4">
      <div className="text-sm font-medium text-foreground">
        {t.delivery.projectIntegrations.targetRepoSectionTitle(forgeLabel)}
      </div>
      <p className="text-sm text-(--ui-text-secondary)">
        {t.delivery.projectIntegrations.targetRepoSectionDescription}
      </p>
      <div className="max-w-xl space-y-2">
        <label className="text-sm font-medium" htmlFor="target-vcs-repo">
          {t.delivery.projectIntegrations.targetRepoLabel}
        </label>
        <Select
          disabled={reposLoading || repoSaving || vcsRepos.length === 0}
          onValueChange={value => void handleDefaultRepoChange(value)}
          value={defaultRepo || undefined}
        >
          <SelectTrigger className="h-9 rounded-md" id="target-vcs-repo">
            <SelectValue placeholder={t.delivery.projectIntegrations.targetRepoPlaceholder} />
          </SelectTrigger>
          <SelectContent>
            {vcsRepos.map(repo => (
              <SelectItem key={repo.path} value={repo.path}>
                {repo.path}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-(--ui-text-tertiary)">
          {reposLoading
            ? t.delivery.projectIntegrations.targetRepoLoading(forgeLabel)
            : repoSaving
              ? t.delivery.projectIntegrations.targetRepoSaving
              : vcsRepos.length === 0
                ? t.delivery.projectIntegrations.targetRepoEmpty(forgeLabel)
                : t.delivery.projectIntegrations.targetRepoSavedHint}
        </p>
      </div>

      <div className="max-w-xl space-y-2 border-t border-(--ui-border-subtle) pt-4">
        <div className="text-sm font-medium text-foreground">
          {t.delivery.projectIntegrations.mergeTargetSectionTitle}
        </div>
        <p className="text-sm text-(--ui-text-secondary)">
          {t.delivery.projectIntegrations.mergeTargetSectionDescription(forgeLabel, reviewRequestLabel)}
        </p>
        <label className="text-sm font-medium" htmlFor="merge-target-branch">
          {t.delivery.projectIntegrations.mergeTargetLabel}
        </label>
        <Input
          disabled={reposLoading || branchSaving}
          id="merge-target-branch"
          onBlur={() => void handleIntegrationBranchSave()}
          onChange={event => setIntegrationBranch(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter') {
              event.preventDefault()
              void handleIntegrationBranchSave()
            }
          }}
          placeholder={t.delivery.projectIntegrations.mergeTargetPlaceholder}
          value={integrationBranch}
        />
        <p className="text-xs text-(--ui-text-tertiary)">
          {branchSaving
            ? t.delivery.projectIntegrations.mergeTargetSaving
            : t.delivery.projectIntegrations.mergeTargetSavedHint(reviewRequestLabel)}
        </p>
      </div>
    </div>
  )

  return (
    <>
      <ManagerSection icon={Link2} title="Integrations">
        <div className="space-y-4 p-4">
          <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-4">
            <div className="text-sm font-medium text-foreground">
              {t.delivery.projectIntegrations.vcsProviderSectionTitle}
            </div>
            <p className="mt-1 text-sm text-(--ui-text-secondary)">
              {t.delivery.projectIntegrations.vcsProviderSectionDescription}
            </p>
            <div className="mt-4 max-w-xs space-y-2">
              <label className="text-sm font-medium" htmlFor="vcs-provider">
                {t.delivery.projectIntegrations.vcsProviderLabel}
              </label>
              <Select
                disabled={vcsProviderSaving}
                onValueChange={value => void handleVcsProviderChange(normalizeVcsProvider(value))}
                value={vcsProvider}
              >
                <SelectTrigger className="h-9 rounded-md" id="vcs-provider">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="gitlab">{t.delivery.projectIntegrations.vcsProviderGitLab}</SelectItem>
                  <SelectItem value="github">{t.delivery.projectIntegrations.vcsProviderGitHub}</SelectItem>
                </SelectContent>
              </Select>
              {vcsProviderSaving ? (
                <p className="text-xs text-(--ui-text-tertiary)">{t.delivery.projectIntegrations.vcsProviderSaving}</p>
              ) : null}
            </div>
          </div>

          <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-4">
            <div className="text-sm font-medium text-foreground">Jira</div>
            <p className="mt-1 text-sm text-(--ui-text-secondary)">
              {t.delivery.projectIntegrations.jiraSectionDescription(linkedJiraProjectLabel)}
            </p>
            <p className="mt-2 text-xs text-(--ui-text-tertiary)">{jiraStatusLabel}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                disabled={jiraStatus === 'loading' || jiraConnecting || jiraStatus === 'connected'}
                onClick={() => void openConnectDialog('jira')}
                size="sm"
                {...dashboardPrimaryButtonProps()}
              >
                {integrationConnectLabel({
                  connectedLabel: t.delivery.projectIntegrations.jiraConnected,
                  connectLabel: t.delivery.projectIntegrations.connectJira,
                  status: jiraStatus,
                  updateLabel: t.delivery.projectIntegrations.updateJiraCredentials
                })}
              </Button>
              {jiraStatus === 'connected' ? (
                <Button
                  disabled={jiraConnecting}
                  onClick={() => void openConnectDialog('jira')}
                  size="sm"
                  {...dashboardOutlineButtonProps()}
                >
                  {t.delivery.projectIntegrations.updateJiraCredentials}
                </Button>
              ) : null}
            </div>

            {jiraStatus === 'connected' ? (
              <div className="mt-5 space-y-3 border-t border-(--ui-border-subtle) pt-4">
                <div className="text-sm font-medium text-foreground">
                  {t.delivery.projectIntegrations.targetJiraSectionTitle}
                </div>
                <p className="text-sm text-(--ui-text-secondary)">
                  {t.delivery.projectIntegrations.targetJiraSectionDescription}
                </p>
                <div className="max-w-xl space-y-2">
                  <label className="text-sm font-medium" htmlFor="linked-jira-project">
                    {t.delivery.projectIntegrations.targetJiraLabel}
                  </label>
                  <Select
                    disabled={jiraProjectsLoading || jiraProjectSaving || jiraProjects.length === 0}
                    onValueChange={value => void handleLinkedJiraProjectChange(value)}
                    value={linkedJiraProjectKey || undefined}
                  >
                    <SelectTrigger className="h-9 rounded-md" id="linked-jira-project">
                      <SelectValue placeholder={t.delivery.projectIntegrations.targetJiraPlaceholder} />
                    </SelectTrigger>
                    <SelectContent>
                      {jiraProjects.map(project => (
                        <SelectItem key={project.key} value={project.key}>
                          {project.name} ({project.key})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-(--ui-text-tertiary)">
                    {jiraProjectsLoading
                      ? t.delivery.projectIntegrations.targetJiraLoading
                      : jiraProjectSaving
                        ? t.delivery.projectIntegrations.targetJiraSaving
                        : jiraProjects.length === 0
                          ? t.delivery.projectIntegrations.targetJiraEmpty
                          : t.delivery.projectIntegrations.targetJiraSavedHint}
                  </p>
                </div>
              </div>
            ) : null}
          </div>

          {vcsProvider === 'gitlab' ? (
            <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-4">
              <div className="text-sm font-medium text-foreground">GitLab</div>
              <p className="mt-1 text-sm text-(--ui-text-secondary)">
                {t.delivery.projectIntegrations.forgeSectionDescription(forgeLabel, reviewRequestLabel)}
              </p>
              <p className="mt-2 text-xs text-(--ui-text-tertiary)">{gitlabStatusLabel}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  disabled={gitlabStatus === 'loading' || gitlabConnecting || gitlabStatus === 'connected'}
                  onClick={() => void openConnectDialog('gitlab')}
                  size="sm"
                  {...dashboardPrimaryButtonProps()}
                >
                  {integrationConnectLabel({
                    connectedLabel: t.delivery.projectIntegrations.gitlabConnected,
                    connectLabel: t.delivery.projectIntegrations.connectGitLab,
                    status: gitlabStatus,
                    updateLabel: t.delivery.projectIntegrations.updateGitLabCredentials
                  })}
                </Button>
                {gitlabStatus === 'connected' ? (
                  <Button
                    disabled={gitlabConnecting}
                    onClick={() => void openConnectDialog('gitlab')}
                    size="sm"
                    {...dashboardOutlineButtonProps()}
                  >
                    {t.delivery.projectIntegrations.updateGitLabCredentials}
                  </Button>
                ) : null}
              </div>

              {gitlabStatus === 'connected' ? renderForgeRepoSettings() : null}
            </div>
          ) : (
            <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-4">
              <div className="text-sm font-medium text-foreground">GitHub</div>
              <p className="mt-1 text-sm text-(--ui-text-secondary)">
                {t.delivery.projectIntegrations.forgeSectionDescription(forgeLabel, reviewRequestLabel)}
              </p>
              <p className="mt-2 text-xs text-(--ui-text-tertiary)">{githubStatusLabel}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  disabled={githubStatus === 'loading' || githubConnecting || githubStatus === 'connected'}
                  onClick={() => void openConnectDialog('github')}
                  size="sm"
                  {...dashboardPrimaryButtonProps()}
                >
                  {integrationConnectLabel({
                    connectedLabel: t.delivery.projectIntegrations.githubConnected,
                    connectLabel: t.delivery.projectIntegrations.connectGitHub,
                    status: githubStatus,
                    updateLabel: t.delivery.projectIntegrations.updateGitHubCredentials
                  })}
                </Button>
                {githubStatus === 'connected' ? (
                  <Button
                    disabled={githubConnecting}
                    onClick={() => void openConnectDialog('github')}
                    size="sm"
                    {...dashboardOutlineButtonProps()}
                  >
                    {t.delivery.projectIntegrations.updateGitHubCredentials}
                  </Button>
                ) : null}
              </div>

              {githubStatus === 'connected' ? renderForgeRepoSettings() : null}
            </div>
          )}

          <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-4">
            <div className="text-sm font-medium text-foreground">
              {t.delivery.projectIntegrations.automationSectionTitle}
            </div>
            <p className="mt-1 text-sm text-(--ui-text-secondary)">
              {t.delivery.projectIntegrations.automationSectionDescription}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Tip label={automationDisabledTooltip}>
                <span className="inline-flex">
                  <Button
                    disabled={!activeProjectKey || !automationPrerequisitesMet || automationSetupBusy}
                    onClick={() => void handleSetupAutomation()}
                    size="sm"
                    {...dashboardPrimaryButtonProps()}
                  >
                    {automationSetupBusy
                      ? t.delivery.projectIntegrations.setupAutomationBusy
                      : t.delivery.projectIntegrations.setupAutomation}
                  </Button>
                </span>
              </Tip>
            </div>
          </div>

          <div className="rounded-lg border border-(--ui-border-subtle) bg-(--ui-chat-surface-background) p-4">
            <div className="text-sm font-medium text-foreground">Other MCP servers</div>
            <p className="mt-1 text-sm text-(--ui-text-secondary)">
              Configure additional stdio or HTTP MCP servers in the global MCP settings.
            </p>
            <div className="mt-4">
              <Button asChild size="sm" {...dashboardOutlineButtonProps()}>
                <Link to={`${SETTINGS_ROUTE}?tab=mcp`}>Open MCP settings</Link>
              </Button>
            </div>
          </div>
        </div>
      </ManagerSection>

      <JiraApiTokenDialog
        busy={jiraConnecting}
        initialValues={jiraSavedCredentials}
        mode={jiraStatus === 'configured' ? 'edit' : 'connect'}
        onClose={() => setJiraDialogOpen(false)}
        onSubmit={handleJiraConnect}
        open={jiraDialogOpen}
      />

      <GitLabTokenDialog
        busy={gitlabConnecting}
        initialValues={gitlabSavedCredentials}
        mode={gitlabStatus === 'configured' ? 'edit' : 'connect'}
        onClose={() => setGitlabDialogOpen(false)}
        onSubmit={handleGitlabConnect}
        open={gitlabDialogOpen}
      />

      <GitHubTokenDialog
        busy={githubConnecting}
        initialValues={githubSavedCredentials}
        mode={githubStatus === 'configured' ? 'edit' : 'connect'}
        onClose={() => setGithubDialogOpen(false)}
        onSubmit={handleGithubConnect}
        open={githubDialogOpen}
      />
    </>
  )
}
