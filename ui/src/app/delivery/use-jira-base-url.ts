import { useStore } from '@nanostores/react'
import { useEffect, useState } from 'react'

import { resolveJiraBaseUrl } from '@/lib/jira-dashboard-transport'
import { $projectConfigRevision } from '@/store/project-config'

export function useJiraBaseUrl(): string | null {
  const projectConfigRevision = useStore($projectConfigRevision)
  const [jiraUrl, setJiraUrl] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    void (async () => {
      try {
        const resolved = await resolveJiraBaseUrl()
        if (!cancelled) {
          setJiraUrl(resolved)
        }
      } catch {
        if (!cancelled) {
          setJiraUrl(null)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [projectConfigRevision])

  return jiraUrl
}
