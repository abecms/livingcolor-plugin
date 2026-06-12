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
    <a
      className={cn(
        'group inline-flex cursor-pointer items-start gap-1.5 text-inherit no-underline decoration-white/35 underline-offset-[3px] transition-colors hover:text-foreground hover:underline',
        className
      )}
      href={href}
      onClick={event => {
        event.preventDefault()
        openExternalLink(href)
      }}
      rel="noopener noreferrer"
      target="_blank"
      title={`Open ${jiraKey} in Jira`}
    >
      <span>{children}</span>
      <ArrowUpRight className="mt-0.5 size-3.5 shrink-0 text-(--ui-text-tertiary) opacity-70 transition-opacity group-hover:text-foreground group-hover:opacity-100" />
    </a>
  )
}
