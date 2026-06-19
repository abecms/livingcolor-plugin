import { afterEach, describe, expect, it, vi } from 'vitest'

import { openExternalLink } from './external-link'

describe('openExternalLink', () => {
  afterEach(() => {
    delete window.livingColorDesktop
    vi.restoreAllMocks()
  })

  it('falls back to window.open when no desktop bridge is available', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue({} as Window)

    openExternalLink('https://jira.example.com/browse/TVP-2138')

    expect(open).toHaveBeenCalledWith('https://jira.example.com/browse/TVP-2138', '_blank', 'noopener,noreferrer')
  })

  it('does not navigate the current page when window.open is unavailable', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null)

    openExternalLink('https://jira.example.com/browse/TVP-2138')

    expect(open).toHaveBeenCalledOnce()
  })

  it('uses the desktop bridge when present', () => {
    const bridge = vi.fn()
    window.livingColorDesktop = { openExternal: bridge }

    openExternalLink('https://jira.example.com/browse/TVP-2138')

    expect(bridge).toHaveBeenCalledWith('https://jira.example.com/browse/TVP-2138')
  })
})
