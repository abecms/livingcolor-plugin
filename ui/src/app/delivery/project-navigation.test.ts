import { describe, expect, it } from 'vitest'

import {
  getProjectRedirectOnOrgChange,
  isProjectDashboardPath,
  isProjectTabActive,
  parseProjectKeyFromPath,
  projectRoute,
  projectTabRoute
} from './project-navigation'

describe('project-navigation', () => {
  it('builds project routes', () => {
    expect(projectRoute('bn')).toBe('/projects/BN')
    expect(projectTabRoute('BN', '/settings')).toBe('/projects/BN/settings')
  })

  it('parses project key from pathname', () => {
    expect(parseProjectKeyFromPath('/projects/BN/settings')).toBe('BN')
    expect(parseProjectKeyFromPath('/dashboard')).toBeNull()
  })

  it('detects active tabs', () => {
    expect(isProjectTabActive('/projects/BN', 'BN', '')).toBe(true)
    expect(isProjectTabActive('/projects/BN/settings', 'BN', '/settings')).toBe(true)
    expect(isProjectTabActive('/projects/BN/integrations', 'BN', '/integrations')).toBe(true)
  })

  it('detects the project dashboard path', () => {
    expect(isProjectDashboardPath('/projects/BN')).toBe(true)
    expect(isProjectDashboardPath('/projects/BN/')).toBe(true)
    expect(isProjectDashboardPath('/projects/BN/settings')).toBe(false)
    expect(isProjectDashboardPath('/projects/BN/chat')).toBe(false)
  })

  it('redirects to the first project after an org switch when the current project is missing', () => {
    expect(
      getProjectRedirectOnOrgChange('/projects/BN/settings', [{ id: 'TV5' }, { id: 'APP' }])
    ).toBe('/projects/TV5/settings')
  })

  it('keeps the current route when the project belongs to the active org', () => {
    expect(getProjectRedirectOnOrgChange('/projects/BN', [{ id: 'BN' }])).toBeNull()
  })

  it('redirects to home when the org has no projects', () => {
    expect(getProjectRedirectOnOrgChange('/projects/BN/settings', [])).toBe('/')
  })
})
