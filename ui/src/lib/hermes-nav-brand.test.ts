import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { installHermesNavBrand } from '@/lib/hermes-nav-brand'

describe('installHermesNavBrand', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <aside id="app-sidebar">
        <a href="/livingcolor">
          <svg class="lucide" />
          <span>LivingColor</span>
        </a>
      </aside>
    `
    ;(window as Window & { __HERMES_BASE_PATH__?: string }).__HERMES_BASE_PATH__ = ''
  })

  afterEach(() => {
    document.body.innerHTML = ''
    vi.restoreAllMocks()
  })

  it('replaces the Lucide svg with the brand frog image', () => {
    installHermesNavBrand()

    const link = document.querySelector<HTMLAnchorElement>('a[href="/livingcolor"]')
    expect(link?.querySelector('svg')).toBeNull()

    const img = link?.querySelector('img.lc-hermes-nav-frog')
    expect(img).not.toBeNull()
    expect(img?.getAttribute('src')).toBe('/dashboard-plugins/livingcolor/dist/livingcolor-frog.png')
  })
})
