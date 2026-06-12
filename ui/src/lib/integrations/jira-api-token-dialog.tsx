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
import { JIRA_ATLASSIAN_API_TOKEN_URL } from '@/lib/jira-mcp'
import { openExternalLink } from '@/lib/external-link'

export interface JiraCredentialsFormValues {
  apiToken: string
  jiraUrl: string
  username: string
}

interface JiraApiTokenDialogProps {
  busy: boolean
  initialValues?: Partial<JiraCredentialsFormValues> | null
  mode?: 'connect' | 'edit'
  onClose: () => void
  onSubmit: (values: JiraCredentialsFormValues) => Promise<boolean>
  open: boolean
}

export function JiraApiTokenDialog({
  busy,
  initialValues = null,
  mode = 'connect',
  onClose,
  onSubmit,
  open
}: JiraApiTokenDialogProps) {
  const [jiraUrl, setJiraUrl] = useState('')
  const [username, setUsername] = useState('')
  const [apiToken, setApiToken] = useState('')
  const editing = mode === 'edit'

  useEffect(() => {
    if (!open) {
      return
    }

    setJiraUrl(initialValues?.jiraUrl?.trim() ?? '')
    setUsername(initialValues?.username?.trim() ?? '')
    setApiToken('')
  }, [initialValues, open])

  const handleSubmit = async () => {
    if (!jiraUrl.trim() || !username.trim() || !apiToken.trim()) {
      return
    }

    const ok = await onSubmit({
      apiToken: apiToken.trim(),
      jiraUrl: jiraUrl.trim(),
      username: username.trim()
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
          <DialogTitle>{editing ? 'Update Jira credentials' : 'Connect Jira'}</DialogTitle>
          <DialogDescription>
            Same setup as Cursor MCP: your Jira site URL, Atlassian account email, and a personal API
            token. LivingColor runs <code className="text-xs">uvx mcp-atlassian</code> in the
            background.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="jira-url">
              JIRA_URL
            </label>
            <Input
              autoComplete="url"
              disabled={busy}
              id="jira-url"
              onChange={event => setJiraUrl(event.target.value)}
              placeholder="https://afp-jira.atlassian.net/"
              type="url"
              value={jiraUrl}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="jira-username">
              JIRA_USERNAME
            </label>
            <Input
              autoComplete="email"
              disabled={busy}
              id="jira-username"
              onChange={event => setUsername(event.target.value)}
              placeholder="you@company.com"
              type="email"
              value={username}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="jira-api-token">
              JIRA_API_TOKEN
            </label>
            <Input
              autoComplete="off"
              disabled={busy}
              id="jira-api-token"
              onChange={event => setApiToken(event.target.value)}
              placeholder={editing ? 'Paste a new token to replace the saved one' : 'Atlassian API token'}
              type="password"
              value={apiToken}
            />
          </div>

          <Button
            className="px-0"
            disabled={busy}
            onClick={() => openExternalLink(JIRA_ATLASSIAN_API_TOKEN_URL)}
            size="sm"
            type="button"
            variant="link"
          >
            Create API token on Atlassian
          </Button>
        </div>

        <DialogFooter>
          <Button disabled={busy} onClick={onClose} type="button" variant="outline">
            Cancel
          </Button>
          <Button
            disabled={busy || !jiraUrl.trim() || !username.trim() || !apiToken.trim()}
            onClick={() => void handleSubmit()}
            type="button"
          >
            {busy ? 'Saving…' : editing ? 'Save credentials' : 'Connect'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
