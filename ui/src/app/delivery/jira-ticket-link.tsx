import type { ReactNode } from 'react'

import { buildJiraIssueBrowseUrl } from '@/lib/jira-mcp'
import { openExternalLink } from '@/lib/external-link'
import { ArrowUpRight } from '@/lib/icons'
import { cn } from '@/lib/utils'

import { useJiraBrowseBaseUrl } from './jira-browse-context'

export function JiraTicketTitleLink({
  children,
  className,
  jiraKey
}: {
  children: ReactNode
  className?: string
  jiraKey: string
}) {
  const jiraBaseUrl = useJiraBrowseBaseUrl()
  const href = buildJiraIssueBrowseUrl(jiraKey, jiraBaseUrl)

  if (!href) {
    return <span className={className}>{children}</span>
  }

  return (
    <button
      className={cn(
        'group inline-flex cursor-pointer items-start gap-1.5 border-0 bg-transparent p-0 text-left text-inherit no-underline decoration-muted-foreground underline-offset-[3px] transition-colors hover:text-foreground hover:underline',
        className
      )}
      onClick={event => {
        event.preventDefault()
        event.stopPropagation()
        openExternalLink(href)
      }}
      title={`Open ${jiraKey} in Jira`}
      type="button"
    >
      <span>{children}</span>
      <ArrowUpRight className="mt-0.5 size-3.5 shrink-0 text-(--ui-text-tertiary) opacity-70 transition-opacity group-hover:text-foreground group-hover:opacity-100" />
    </button>
  )
}
