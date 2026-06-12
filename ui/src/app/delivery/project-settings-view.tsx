import { useCallback, useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  DEFAULT_TICKET_SCOPE,
  fetchProjectConfig,
  saveProjectConfig,
  type TicketScopePayload
} from '@/lib/delivery'
import { useFirebaseAuth } from '@/hooks/use-firebase-auth'
import { Settings, Share2, SlidersHorizontal, Trash2 } from '@/lib/icons'
import { bumpProjectConfigRevision } from '@/store/project-config'
import { notifyError, notify } from '@/store/notifications'

import { ManagerPageHeader, ManagerPageShell, ManagerSection } from '../manager-page-layout'

import { dashboardOutlineButtonProps, dashboardPrimaryButtonProps } from './dashboard-ui'
import { ShareProjectDialog } from './share-project-dialog'
import { useProjectWorkspace } from '@/hooks/use-project-workspace'

export function ProjectSettingsView() {
  const { enabled, status } = useFirebaseAuth()
  const { activeProject, activeProjectKey, deleteProject, refreshProjects } = useProjectWorkspace()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState('')
  const [projectName, setProjectName] = useState('')
  const [projectKey, setProjectKey] = useState('')
  const [durationDays, setDurationDays] = useState('14')
  const [capacityDays, setCapacityDays] = useState('15')
  const [communicationLanguage, setCommunicationLanguage] = useState<'en' | 'fr'>('fr')
  const [ticketScope, setTicketScope] = useState<TicketScopePayload>(DEFAULT_TICKET_SCOPE)
  const [assigneeInput, setAssigneeInput] = useState('')
  const [configPath, setConfigPath] = useState('')
  const [shareOpen, setShareOpen] = useState(false)

  const displayName = activeProject?.projectName ?? projectName
  const displayKey = activeProjectKey ?? projectKey

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const config = await fetchProjectConfig()
      setProjectKey(config.projectKey)
      setProjectName(config.projectName)
      setDurationDays(String(config.sprintDurationDays))
      setCapacityDays(String(config.sprintCapacityDays))
      setCommunicationLanguage(config.communicationLanguage === 'en' ? 'en' : 'fr')
      setTicketScope(config.ticketScope ?? DEFAULT_TICKET_SCOPE)
      setAssigneeInput((config.ticketScope?.assignees ?? []).join(', '))
      setConfigPath(config.configPath)
    } catch (error) {
      notifyError(error, 'Project settings could not be loaded')
    } finally {
      setLoading(false)
    }
  }, [activeProjectKey])

  useEffect(() => {
    void load()
  }, [load, activeProjectKey])

  const save = useCallback(async () => {
    const parsedDuration = Number.parseInt(durationDays, 10)
    const parsedCapacity = Number.parseFloat(capacityDays)
    if (!Number.isFinite(parsedDuration) || parsedDuration < 1) {
      notifyError(new Error('Invalid sprint duration'), 'Enter a sprint duration of at least 1 day')
      return
    }
    if (!Number.isFinite(parsedCapacity) || parsedCapacity < 0.5) {
      notifyError(new Error('Invalid capacity'), 'Enter a capacity of at least 0.5 person-days')
      return
    }

    const assignees = assigneeInput
      .split(',')
      .map(value => value.trim())
      .filter(Boolean)
    const scopePayload: TicketScopePayload = {
      ...ticketScope,
      assignees
    }

    setSaving(true)
    try {
      const config = await saveProjectConfig({
        sprintDurationDays: parsedDuration,
        sprintCapacityDays: parsedCapacity,
        communicationLanguage,
        ticketScope: scopePayload
      })
      setDurationDays(String(config.sprintDurationDays))
      setCapacityDays(String(config.sprintCapacityDays))
      setCommunicationLanguage(config.communicationLanguage === 'en' ? 'en' : 'fr')
      setTicketScope(config.ticketScope ?? DEFAULT_TICKET_SCOPE)
      setAssigneeInput((config.ticketScope?.assignees ?? []).join(', '))
      setConfigPath(config.configPath)
      bumpProjectConfigRevision()
      notify({
        kind: 'success',
        message: 'Project settings saved. Jira comment proposals were refreshed in the selected language.'
      })
    } catch (error) {
      notifyError(error, 'Could not save project settings')
    } finally {
      setSaving(false)
    }
  }, [assigneeInput, capacityDays, communicationLanguage, durationDays, ticketScope])

  const toggleStatusGroup = useCallback((group: 'todo' | 'in_progress', checked: boolean) => {
    setTicketScope(current => {
      const groups = new Set(current.statusGroups)
      if (checked) {
        groups.add(group)
      } else {
        groups.delete(group)
      }
      return {
        ...current,
        statusGroups: groups.size > 0 ? [...groups] : ['todo']
      }
    })
  }, [])

  const handleDelete = useCallback(async () => {
    if (!activeProjectKey || deleteConfirm !== 'delete') {
      return
    }
    setDeleting(true)
    try {
      await deleteProject(activeProjectKey)
      notify({ kind: 'success', message: 'Project removed from workspace.' })
    } catch (error) {
      notifyError(error, 'Could not delete project')
    } finally {
      setDeleting(false)
      setDeleteConfirm('')
    }
  }, [activeProjectKey, deleteConfirm, deleteProject])

  return (
    <ManagerPageShell wide={false}>
      <ManagerPageHeader
        description="Configure sprint capacity, ticket scope, and communication defaults for this Jira project."
        eyebrow={`${displayKey} · ${displayName}`}
        icon={Settings}
        title="Project Settings"
      />

      <ManagerSection icon={Settings} title="Sprint Configuration">
        <div className="space-y-6 p-4">
          <p className="text-sm text-(--ui-text-secondary)">
            These values define how LivingColor plans executable work for {displayName}.
          </p>

          <div className="grid max-w-md gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="sprint-duration">
                Sprint duration (days)
              </label>
              <Input
                disabled={loading || saving}
                id="sprint-duration"
                inputMode="numeric"
                min={1}
                onChange={event => setDurationDays(event.target.value)}
                type="number"
                value={durationDays}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="sprint-capacity">
                Capacity (person-days)
              </label>
              <Input
                disabled={loading || saving}
                id="sprint-capacity"
                inputMode="decimal"
                min={0.5}
                onChange={event => setCapacityDays(event.target.value)}
                step="0.5"
                type="number"
                value={capacityDays}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="communication-language">
                Communication language
              </label>
              <Select
                disabled={loading || saving}
                onValueChange={value => setCommunicationLanguage(value === 'en' ? 'en' : 'fr')}
                value={communicationLanguage}
              >
                <SelectTrigger className="h-9 rounded-md" id="communication-language">
                  <SelectValue placeholder="Select a language" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="fr">French — comments, MRs, stakeholder emails</SelectItem>
                  <SelectItem value="en">English — comments, MRs, stakeholder emails</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-(--ui-text-tertiary)">
                Used for Jira comment proposals, merge request drafts, and dashboard stakeholder updates.
              </p>
            </div>
          </div>
        </div>
      </ManagerSection>

      <ManagerSection icon={SlidersHorizontal} title="Ticket scope">
        <div className="space-y-6 p-4">
          <p className="text-sm text-(--ui-text-secondary)">
            Choose which Jira tickets LivingColor scans, analyzes, and automates for {displayName}.
          </p>

          <div className="grid max-w-xl gap-5">
            <div className="space-y-3">
              <p className="text-sm font-medium">Statuses</p>
              <label className="flex items-center gap-3 text-sm">
                <Checkbox
                  checked={ticketScope.statusGroups.includes('todo')}
                  disabled={loading || saving}
                  onCheckedChange={value => toggleStatusGroup('todo', value === true)}
                />
                <span>To Do / À faire / Backlog / Rouvert</span>
              </label>
              <label className="flex items-center gap-3 text-sm">
                <Checkbox
                  checked={ticketScope.statusGroups.includes('in_progress')}
                  disabled={loading || saving}
                  onCheckedChange={value => toggleStatusGroup('in_progress', value === true)}
                />
                <span>In progress / En cours</span>
              </label>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="ticket-assignees">
                Assignees (optional)
              </label>
              <Input
                disabled={loading || saving}
                id="ticket-assignees"
                onChange={event => {
                  const value = event.target.value
                  setAssigneeInput(value)
                  if (value.trim()) {
                    setTicketScope(current => ({ ...current, includeUnassigned: false }))
                  }
                }}
                placeholder="e.g. Ada Lovelace, Bob Martin"
                value={assigneeInput}
              />
              <p className="text-xs text-(--ui-text-tertiary)">
                Use exact Jira display names, comma-separated. Unassigned tickets are excluded by
                default when assignees are set. After saving, run a new readiness scan.
              </p>
            </div>

            <label className="flex items-center gap-3 text-sm">
              <Checkbox
                checked={ticketScope.includeUnassigned}
                disabled={loading || saving || assigneeInput.trim().length === 0}
                onCheckedChange={value =>
                  setTicketScope(current => ({ ...current, includeUnassigned: value === true }))
                }
              />
              <span>Include unassigned tickets when filtering by assignee</span>
            </label>

            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="ticket-match-mode">
                When status and assignee filters are both set
              </label>
              <Select
                disabled={loading || saving}
                onValueChange={value =>
                  setTicketScope(current => ({
                    ...current,
                    matchMode: value === 'any' ? 'any' : 'all'
                  }))
                }
                value={ticketScope.matchMode}
              >
                <SelectTrigger className="h-9 rounded-md" id="ticket-match-mode">
                  <SelectValue placeholder="Match mode" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Match all criteria (AND)</SelectItem>
                  <SelectItem value="any">Match any criterion (OR)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 border-t border-(--ui-border-subtle) pt-4">
            <Button disabled={loading || saving} onClick={() => void save()} {...dashboardPrimaryButtonProps()}>
              {saving ? 'Saving…' : 'Save settings'}
            </Button>
            <Button disabled={loading || saving} onClick={() => void load()} {...dashboardOutlineButtonProps()}>
              Reload
            </Button>
          </div>

          {configPath ? (
            <p className="text-xs text-(--ui-text-tertiary)">
              Sprint and ticket scope are saved together to{' '}
              <code className="text-(--ui-text-secondary)">{configPath}</code>
            </p>
          ) : (
            <p className="text-xs text-(--ui-text-tertiary)">
              Sprint and ticket scope are saved together when you click Save settings.
            </p>
          )}
        </div>
      </ManagerSection>

      {enabled && status === 'signed-in' && activeProject?.storage !== 'cloud' ? (
        <ManagerSection icon={Share2} title="Move to organization">
          <div className="space-y-4 p-4">
            <p className="text-sm text-(--ui-text-secondary)">
              Transfer this personal project to a team organization. It will disappear from your personal
              project list and only remain available inside that organization.
            </p>
            <Button
              disabled={!activeProjectKey}
              onClick={() => setShareOpen(true)}
              {...dashboardOutlineButtonProps()}
            >
              <Share2 className="mr-2 size-4" />
              Move to organization
            </Button>
          </div>
          <ShareProjectDialog
            jiraProjectKey={displayKey}
            onOpenChange={setShareOpen}
            onShared={() => void refreshProjects()}
            open={shareOpen}
            projectName={displayName}
          />
        </ManagerSection>
      ) : null}

      <ManagerSection icon={Trash2} title="Danger Zone">
        <div className="space-y-4 p-4">
          <p className="text-sm text-(--ui-text-secondary)">
            Remove this project from the workspace. Delivery history in Jira is not affected.
          </p>
          <div className="grid max-w-md gap-3">
            <Input
              disabled={deleting}
              onChange={event => setDeleteConfirm(event.target.value)}
              placeholder='Type "delete" to confirm'
              value={deleteConfirm}
            />
            <Button
              disabled={deleting || deleteConfirm !== 'delete' || !activeProjectKey}
              onClick={() => void handleDelete()}
              variant="destructive"
            >
              {deleting ? 'Deleting…' : 'Delete project'}
            </Button>
          </div>
        </div>
      </ManagerSection>
    </ManagerPageShell>
  )
}
