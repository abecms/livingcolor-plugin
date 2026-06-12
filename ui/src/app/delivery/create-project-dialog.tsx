import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { notifyError } from '@/store/notifications'

import { dashboardOutlineButtonProps, dashboardPrimaryButtonProps } from './dashboard-ui'
import { useProjectWorkspace } from '@/hooks/use-project-workspace'

export function CreateProjectDialog({
  open,
  onOpenChange
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { createProject } = useProjectWorkspace()
  const [projectName, setProjectName] = useState('')
  const [jiraProjectKey, setJiraProjectKey] = useState('')
  const [creating, setCreating] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setCreating(true)
    try {
      await createProject(jiraProjectKey, projectName)
      setProjectName('')
      setJiraProjectKey('')
      onOpenChange(false)
    } catch (error) {
      notifyError(error, 'Could not create project')
    } finally {
      setCreating(false)
    }
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={event => void handleSubmit(event)}>
          <DialogHeader>
            <DialogTitle>Create project</DialogTitle>
            <DialogDescription>
              Add a Jira project to this workspace. You can configure sprint settings and integrations after creation.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="create-project-name">
                Project name
              </label>
              <Input
                autoFocus
                disabled={creating}
                id="create-project-name"
                onChange={event => setProjectName(event.target.value)}
                placeholder="Bibliothèque Numérique"
                required
                value={projectName}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="create-project-key">
                Jira project key
              </label>
              <Input
                disabled={creating}
                id="create-project-key"
                onChange={event => setJiraProjectKey(event.target.value.toUpperCase())}
                placeholder="BN"
                required
                value={jiraProjectKey}
              />
            </div>
          </div>

          <DialogFooter>
            <Button disabled={creating} onClick={() => onOpenChange(false)} type="button" {...dashboardOutlineButtonProps()}>
              Cancel
            </Button>
            <Button disabled={creating} type="submit" {...dashboardPrimaryButtonProps()}>
              {creating ? 'Creating…' : 'Create project'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
