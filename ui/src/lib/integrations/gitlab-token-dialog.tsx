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

export interface GitLabCredentialsFormValues {
  apiToken: string
  gitlabUrl: string
}

interface GitLabTokenDialogProps {
  busy: boolean
  initialValues?: Partial<GitLabCredentialsFormValues> | null
  mode?: 'connect' | 'edit'
  onClose: () => void
  onSubmit: (values: GitLabCredentialsFormValues) => Promise<boolean>
  open: boolean
}

export function GitLabTokenDialog({
  busy,
  initialValues = null,
  mode = 'connect',
  onClose,
  onSubmit,
  open
}: GitLabTokenDialogProps) {
  const [gitlabUrl, setGitlabUrl] = useState('')
  const [apiToken, setApiToken] = useState('')
  const editing = mode === 'edit'

  useEffect(() => {
    if (!open) {
      return
    }
    setGitlabUrl(initialValues?.gitlabUrl?.trim() ?? '')
    setApiToken('')
  }, [initialValues, open])

  const handleSubmit = async () => {
    if (!gitlabUrl.trim() || !apiToken.trim()) {
      return
    }
    const ok = await onSubmit({
      apiToken: apiToken.trim(),
      gitlabUrl: gitlabUrl.trim()
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
          <DialogTitle>{editing ? 'Update GitLab credentials' : 'Connect GitLab'}</DialogTitle>
          <DialogDescription>
            GitLab instance URL and a personal access token with API scope for MCP delivery workflows.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <Input onChange={event => setGitlabUrl(event.target.value)} placeholder="https://gitlab.com" value={gitlabUrl} />
          <Input
            onChange={event => setApiToken(event.target.value)}
            placeholder="glpat-..."
            type="password"
            value={apiToken}
          />
        </div>
        <DialogFooter>
          <Button onClick={() => openExternalLink('https://gitlab.com/-/user_settings/personal_access_tokens')} variant="ghost">
            Create token
          </Button>
          <Button disabled={busy || !gitlabUrl.trim() || !apiToken.trim()} onClick={() => void handleSubmit()}>
            {editing ? 'Save' : 'Connect'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
