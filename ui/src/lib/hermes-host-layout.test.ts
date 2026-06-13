import { describe, expect, it } from 'vitest'

import { findHermesPluginShell } from './hermes-host-layout'

describe('findHermesPluginShell', () => {
  it('finds the Hermes page header wrapper above the plugin root', () => {
    document.body.innerHTML = `
      <div class="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden">
        <header role="banner">Hermes page header</header>
        <div class="px-6 pt-6">
          <div class="w-full">
            <div class="lc-root">plugin</div>
          </div>
        </div>
      </div>
    `

    const root = document.querySelector('.lc-root') as HTMLElement
    const shell = findHermesPluginShell(root)

    expect(shell?.header.textContent).toContain('Hermes page header')
    expect(shell?.panel.contains(root)).toBe(true)
  })
})
