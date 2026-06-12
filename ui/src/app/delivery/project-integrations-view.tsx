import { useCallback, useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { fetchPmInbox, fetchProjectConfig, type PmInboxPayload } from '@/lib/delivery'
import { Globe, Settings } from '@/lib/icons'
import { notifyError } from '@/store/notifications'

import { ManagerPageHeader, ManagerPageShell, ManagerSection } from '../manager-page-layout'

import { dashboardPrimaryButtonProps } from './dashboard-ui'
import { ProjectIntegrationsSection } from './project-integrations'
import { useProjectWorkspace } from '@/hooks/use-project-workspace'
import { buildDailyAnalysisLastRunCaption, useDailyAnalysis } from './use-daily-analysis'

export function ProjectIntegrationsView() {
  const { activeProject, activeProjectKey } = useProjectWorkspace()
  const [loading, setLoading] = useState(true)
  const [projectName, setProjectName] = useState('')
  const [projectKey, setProjectKey] = useState('')
  const [lastRun, setLastRun] = useState<PmInboxPayload['lastRun']>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [config, inbox] = await Promise.all([
        fetchProjectConfig(),
        fetchPmInbox(activeProjectKey ?? undefined).catch(() => null)
      ])
      setProjectKey(config.projectKey)
      setProjectName(config.projectName)
      setLastRun(inbox?.lastRun ?? null)
    } catch (error) {
      notifyError(error, 'Project integrations could not be loaded')
    } finally {
      setLoading(false)
    }
  }, [activeProjectKey])

  const { running: analysisRunning, run: runAnalysis } = useDailyAnalysis(load)

  useEffect(() => {
    void load()
  }, [load, activeProjectKey])

  const displayName = activeProject?.projectName ?? projectName
  const displayKey = activeProjectKey ?? projectKey
  const lastRunCaption = buildDailyAnalysisLastRunCaption(lastRun)

  return (
    <ManagerPageShell wide={false}>
      <ManagerPageHeader
        description="Connect Jira and GitLab, then run daily analysis to populate the sprint queue."
        eyebrow={`${displayKey} · ${displayName}`}
        icon={Globe}
        title="Integrations"
      />

      <ProjectIntegrationsSection />

      <ManagerSection icon={Settings} title="Daily Analysis">
        <div className="space-y-4 p-4">
          <p className="text-sm text-(--ui-text-secondary)">
            Sprint capacity alone does not populate the dashboard. Run daily analysis to scan Jira, estimate ready
            tickets, and build the sprint queue shown on the Project Dashboard.
          </p>
          <Button
            disabled={loading || analysisRunning}
            onClick={() => void runAnalysis(displayKey || undefined)}
            {...dashboardPrimaryButtonProps()}
          >
            {analysisRunning ? 'Running analysis…' : 'Run daily analysis'}
          </Button>
          {lastRunCaption ? (
            <p className="text-xs text-(--ui-text-tertiary)">{lastRunCaption}</p>
          ) : null}
        </div>
      </ManagerSection>
    </ManagerPageShell>
  )
}
