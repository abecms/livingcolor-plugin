const JIRA_PROJECT_STORAGE_KEY = 'livingcolor.dashboard.jiraProject'

export function readStoredJiraProjectKey(): string | null {
  if (typeof window === 'undefined') {
    return null
  }

  try {
    const value = window.localStorage.getItem(JIRA_PROJECT_STORAGE_KEY)?.trim()

    return value || null
  } catch {
    return null
  }
}

export function writeStoredJiraProjectKey(projectKey: string | null): void {
  if (typeof window === 'undefined') {
    return
  }

  try {
    if (!projectKey) {
      window.localStorage.removeItem(JIRA_PROJECT_STORAGE_KEY)

      return
    }

    window.localStorage.setItem(JIRA_PROJECT_STORAGE_KEY, projectKey)
  } catch {
    // ignore quota / privacy mode
  }
}
