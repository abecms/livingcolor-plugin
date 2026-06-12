import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'livingcolor.desktop.projectSidebarCollapsed'

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function useProjectSidebarCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(readCollapsed)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0')
    } catch {
      // Ignore storage failures in private browsing.
    }
  }, [collapsed])

  const toggle = useCallback(() => {
    setCollapsed(value => !value)
  }, [])

  return [collapsed, toggle]
}
