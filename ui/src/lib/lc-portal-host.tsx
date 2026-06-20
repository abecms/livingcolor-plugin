/** Overlay portal mount inside `.lc-root` so menus/sheets stack above plugin content. */

export const LC_PORTAL_HOST_ID = 'lc-portal-host'

export function ensureLcPortalHost(root?: HTMLElement | null): HTMLElement | null {
  if (typeof document === 'undefined') {
    return null
  }

  const mountRoot =
    root ?? (document.querySelector('.lc-root') instanceof HTMLElement ? document.querySelector('.lc-root') : null)

  if (!mountRoot) {
    return null
  }

  let host = document.getElementById(LC_PORTAL_HOST_ID)
  if (!host) {
    host = document.createElement('div')
    host.id = LC_PORTAL_HOST_ID
    host.className = 'lc-portal-host'
    host.dataset.slot = 'lc-portal-host'
    mountRoot.appendChild(host)
  } else if (host.parentElement !== mountRoot) {
    mountRoot.appendChild(host)
  }

  return host
}

export function getLcPortalContainer(): HTMLElement | undefined {
  if (typeof document === 'undefined') {
    return undefined
  }

  const existing = document.getElementById(LC_PORTAL_HOST_ID)
  if (existing) {
    return existing
  }

  return ensureLcPortalHost() ?? undefined
}

/** Kept for App tree compatibility; the host is created on `.lc-root` in main.tsx. */
export function LcPortalHost() {
  return null
}
