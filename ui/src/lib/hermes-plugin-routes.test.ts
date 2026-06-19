import { describe, expect, it } from 'vitest'

import { isHermesPluginProjectDashboardPath, parseHermesPluginProjectKey } from './hermes-plugin-routes'

describe('hermes-plugin-routes', () => {
  it('detects the project dashboard route inside the plugin tab', () => {
    expect(isHermesPluginProjectDashboardPath('/livingcolor/projects/BN')).toBe(true)
    expect(isHermesPluginProjectDashboardPath('/livingcolor/projects/BN/settings')).toBe(false)
    expect(isHermesPluginProjectDashboardPath('/chat')).toBe(false)
  })

  it('parses the project key from the Hermes plugin URL', () => {
    expect(parseHermesPluginProjectKey('/livingcolor/projects/bn')).toBe('BN')
  })
})
