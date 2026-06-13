import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { FirebaseLoginPage } from '@/app/auth/firebase-login-page'
import { Check, Layers3, LogIn, Plus } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { notifyError } from '@/store/notifications'
import { useStore } from '@nanostores/react'

import { useFirebaseAuth } from '@/hooks/use-firebase-auth'
import { $workspaceScope, isLocalWorkspaceScope } from '@/store/workspace-scope'

import { dashboardOutlineButtonProps, dashboardPrimaryButtonProps } from './dashboard-ui'

export function WorkspaceOrgSwitcher({
  className,
  iconOnly = false
}: {
  className?: string
  iconOnly?: boolean
}) {
  const {
    activeOrg,
    activeOrgId,
    enabled,
    organizations,
    status,
    createTeam,
    switchOrganization,
    switchToLocalProjects
  } = useFirebaseAuth()
  const workspaceScope = useStore($workspaceScope)
  const [createOpen, setCreateOpen] = useState(false)
  const [signInOpen, setSignInOpen] = useState(false)
  const [teamName, setTeamName] = useState('')
  const [creating, setCreating] = useState(false)
  const isLocal = isLocalWorkspaceScope(workspaceScope)
  const workspaceLabel = isLocal ? 'Personal projects' : activeOrg?.name ?? activeOrgId ?? 'Workspace'

  async function handleCreateTeam(event: FormEvent) {
    event.preventDefault()
    if (!teamName.trim()) {
      return
    }
    setCreating(true)
    try {
      await createTeam(teamName.trim())
      setTeamName('')
      setCreateOpen(false)
    } catch (error) {
      notifyError(error, 'Could not create team workspace')
    } finally {
      setCreating(false)
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            className={cn('justify-start font-normal', className)}
            size={iconOnly ? 'icon' : 'sm'}
            title={iconOnly ? workspaceLabel : undefined}
            variant="ghost"
          >
            <Layers3 className={cn('size-4 shrink-0 text-muted-foreground', !iconOnly && 'mr-2')} />
            {!iconOnly ? <span className="max-w-[140px] truncate text-sm">{workspaceLabel}</span> : null}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          <DropdownMenuItem onClick={switchToLocalProjects}>
            <div className="min-w-0 flex-1">
              <span className="block truncate">Personal projects</span>
              <span className="text-xs text-muted-foreground">Local · no organization</span>
            </div>
            {isLocal ? <Check className="size-4 shrink-0 text-foreground" /> : null}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          {enabled && status === 'signed-out' && organizations.length === 0 ? (
            <DropdownMenuItem onClick={() => setSignInOpen(true)}>
              <LogIn className="mr-2 size-4" />
              Sign in to load team workspaces
            </DropdownMenuItem>
          ) : null}
          {organizations.map(org => (
            <DropdownMenuItem key={org.id} onClick={() => void switchOrganization(org.id)}>
              <div className="min-w-0 flex-1">
                <span className="block truncate">{org.name}</span>
                <span className="text-xs text-muted-foreground">
                  {org.kind === 'personal' ? 'Personal cloud' : 'Team'}
                </span>
              </div>
              {!isLocal && org.id === activeOrgId ? (
                <Check className="size-4 shrink-0 text-foreground" />
              ) : null}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem disabled={!enabled || status !== 'signed-in'} onClick={() => setCreateOpen(true)}>
            <Plus className="mr-2 size-4" />
            Create team workspace
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog onOpenChange={setSignInOpen} open={signInOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
          <FirebaseLoginPage />
        </DialogContent>
      </Dialog>

      <Dialog onOpenChange={setCreateOpen} open={createOpen}>
        <DialogContent className="sm:max-w-md">
          <form onSubmit={event => void handleCreateTeam(event)}>
            <DialogHeader>
              <DialogTitle>Create team workspace</DialogTitle>
            </DialogHeader>
            <div className="py-4">
              <Input
                autoFocus
                disabled={creating}
                onChange={event => setTeamName(event.target.value)}
                placeholder="Team name"
                required
                value={teamName}
              />
            </div>
            <DialogFooter>
              <Button disabled={creating} onClick={() => setCreateOpen(false)} type="button" {...dashboardOutlineButtonProps()}>
                Cancel
              </Button>
              <Button disabled={creating} type="submit" {...dashboardPrimaryButtonProps()}>
                {creating ? 'Creating…' : 'Create'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}
