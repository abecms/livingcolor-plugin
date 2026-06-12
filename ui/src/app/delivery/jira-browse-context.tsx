import { createContext, useContext, type ReactNode } from 'react'

import { useJiraBaseUrl } from './use-jira-base-url'

const JiraBrowseContext = createContext<string | null>(null)

export function JiraBrowseProvider({
  baseUrl: baseUrlOverride,
  children
}: {
  baseUrl?: string | null
  children: ReactNode
}) {
  const resolvedBaseUrl = useJiraBaseUrl()
  const jiraBaseUrl = baseUrlOverride ?? resolvedBaseUrl

  return <JiraBrowseContext.Provider value={jiraBaseUrl}>{children}</JiraBrowseContext.Provider>
}

export function useJiraBrowseBaseUrl(): string | null {
  return useContext(JiraBrowseContext)
}
