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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { useFirebaseAuth } from '@/hooks/use-firebase-auth'
import { shareLocalProjectToOrg } from '@/lib/firebase-session'
import { notify, notifyError } from '@/store/notifications'
import { switchToOrgWorkspace } from '@/store/workspace-scope'

import { dashboardOutlineButtonProps, dashboardPrimaryButtonProps } from './dashboard-ui'

export function ShareProjectDialog({
  open,
  onOpenChange,
  jiraProjectKey,
  projectName,
  onShared
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  jiraProjectKey: string
  projectName: string
  onShared?: () => void
}) {
  const { organizations, switchOrganization } = useFirebaseAuth()
  const [orgId, setOrgId] = useState('')
  const [sharing, setSharing] = useState(false)

  const teamOrgs = organizations.filter(org => org.kind === 'team')
  const targetOrgs = teamOrgs.length > 0 ? teamOrgs : organizations

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!orgId) {
      return
    }
    setSharing(true)
    try {
      await shareLocalProjectToOrg(orgId, jiraProjectKey)
      switchToOrgWorkspace(orgId)
      await switchOrganization(orgId)
      notify({
        kind: 'success',
        message: `${projectName} now lives in the selected organization only.`
      })
      onShared?.()
      onOpenChange(false)
    } catch (error) {
      notifyError(error, 'Could not share project with organization')
    } finally {
      setSharing(false)
    }
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={event => void handleSubmit(event)}>
          <DialogHeader>
            <DialogTitle>Move to organization</DialogTitle>
            <DialogDescription>
              Move {projectName} ({jiraProjectKey}) into an organization you belong to. Repo mapping and
              sprint settings are transferred, and the project is removed from your personal list.
            </DialogDescription>
          </DialogHeader>

          <div className="py-4">
            {targetOrgs.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Create a team workspace first, then share this project with it.
              </p>
            ) : (
              <Select disabled={sharing} onValueChange={setOrgId} value={orgId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select organization" />
                </SelectTrigger>
                <SelectContent>
                  {targetOrgs.map(org => (
                    <SelectItem key={org.id} value={org.id}>
                      {org.name} {org.kind === 'personal' ? '(Personal cloud)' : '(Team)'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <DialogFooter>
            <Button disabled={sharing} onClick={() => onOpenChange(false)} type="button" {...dashboardOutlineButtonProps()}>
              Cancel
            </Button>
            <Button
              disabled={sharing || !orgId || targetOrgs.length === 0}
              type="submit"
              {...dashboardPrimaryButtonProps()}
            >
              {sharing ? 'Moving…' : 'Move to organization'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
