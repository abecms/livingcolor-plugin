import { useEffect, useState } from 'react'

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
import { openExternalLink } from '@/lib/external-link'
import { GITHUB_PERSONAL_ACCESS_TOKEN_URL } from '@/lib/github-mcp'

export interface GitHubCredentialsFormValues {
  apiToken: string
}

interface GitHubTokenDialogProps {
  busy: boolean
  initialValues?: Partial<GitHubCredentialsFormValues> | null
  mode?: 'connect' | 'edit'
  onClose: () => void
  onSubmit: (values: GitHubCredentialsFormValues) => Promise<boolean>
  open: boolean
}

export function GitHubTokenDialog({
  busy,
  initialValues = null,
  mode = 'connect',
  onClose,
  onSubmit,
  open
}: GitHubTokenDialogProps) {
  const [apiToken, setApiToken] = useState('')
  const editing = mode === 'edit'

  useEffect(() => {
    if (!open) {
      return
    }
    setApiToken('')
  }, [initialValues, open])

  const handleSubmit = async () => {
    if (!apiToken.trim()) {
      return
    }
    const ok = await onSubmit({
      apiToken: apiToken.trim()
    })
    if (ok) {
      setApiToken('')
      onClose()
    }
  }

  return (
    <Dialog onOpenChange={next => !next && onClose()} open={open}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{editing ? 'Update GitHub credentials' : 'Connect GitHub'}</DialogTitle>
          <DialogDescription>
            A GitHub personal access token with repository access for MCP delivery workflows.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <label className="text-sm font-medium" htmlFor="github-api-token">
            GitHub token
          </label>
          <Input
            id="github-api-token"
            onChange={event => setApiToken(event.target.value)}
            placeholder="ghp_..."
            type="password"
            value={apiToken}
          />
        </div>
        <DialogFooter>
          <Button onClick={() => openExternalLink(GITHUB_PERSONAL_ACCESS_TOKEN_URL)} variant="ghost">
            Create token
          </Button>
          <Button disabled={busy || !apiToken.trim()} onClick={() => void handleSubmit()}>
            {editing ? 'Save' : 'Connect'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
