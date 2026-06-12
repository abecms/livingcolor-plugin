/** Patch the Hermes host sidebar tab icon for LivingColor (Lucide → brand frog). */

const PLUGIN_NAME = 'livingcolor'
const FROG_ASSET = 'dist/livingcolor-frog.png'
const NAV_ICON_CLASS = 'lc-hermes-nav-frog'

function hermesBasePath(): string {
  const raw = (window as Window & { __HERMES_BASE_PATH__?: string }).__HERMES_BASE_PATH__
  if (typeof raw !== 'string') return ''
  return raw.replace(/\/$/, '')
}

function frogAssetUrl(): string {
  return `${hermesBasePath()}/dashboard-plugins/${PLUGIN_NAME}/${FROG_ASSET}`
}

function findLivingColorNavLink(): HTMLAnchorElement | null {
  const sidebar = document.getElementById('app-sidebar')
  if (!sidebar) return null

  const suffix = '/livingcolor'
  for (const anchor of sidebar.querySelectorAll<HTMLAnchorElement>('a[href]')) {
    const href = anchor.getAttribute('href') ?? ''
    if (href === suffix || href.endsWith(suffix)) {
      return anchor
    }
  }
  return null
}

function patchLivingColorNavIcon(): boolean {
  const link = findLivingColorNavLink()
  if (!link) return false

  const existing = link.querySelector(`.${NAV_ICON_CLASS}`)
  if (existing) return true

  const icon = link.querySelector('svg')
  if (!icon) return false

  const img = document.createElement('img')
  img.src = frogAssetUrl()
  img.alt = ''
  img.width = 14
  img.height = 14
  img.className = `${NAV_ICON_CLASS} h-3.5 w-3.5 shrink-0 object-contain`
  img.decoding = 'async'
  icon.replaceWith(img)
  return true
}

let observer: MutationObserver | null = null

/** Run once the Hermes shell has painted the plugin nav item. */
export function installHermesNavBrand(): void {
  if (typeof document === 'undefined') return

  const tryPatch = () => {
    if (patchLivingColorNavIcon() && observer) {
      observer.disconnect()
      observer = null
    }
  }

  tryPatch()

  if (observer) return

  observer = new MutationObserver(tryPatch)
  const root = document.getElementById('app-sidebar') ?? document.body
  observer.observe(root, { childList: true, subtree: true })
}
