/** Overlay portal mount inside `.lc-root` so menus/sheets stack above plugin content. */

export const LC_PORTAL_HOST_ID = 'lc-portal-host'

export function getLcPortalContainer(): HTMLElement | undefined {
  if (typeof document === 'undefined') {
    return undefined
  }
  return document.getElementById(LC_PORTAL_HOST_ID) ?? undefined
}

export function LcPortalHost() {
  return <div aria-hidden className="lc-portal-host pointer-events-none" id={LC_PORTAL_HOST_ID} />
}
